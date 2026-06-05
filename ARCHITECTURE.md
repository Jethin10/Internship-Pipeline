# ARCHITECTURE.md — Intern Piperline

How the three parts fit together, the data that flows between them, and the
technical decisions behind each. Read `VISION.md` first for the *why*.

---

## 0. System at a glance

```
                         ┌──────────────────────────┐
                         │     Orchestrator / CLI    │
                         │  (runs the pipeline, owns │
                         │   config, scheduling)     │
                         └────────────┬──────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────┐           ┌──────────────────┐          ┌──────────────────┐
│ A. AGGREGATOR │  JobPost  │  C. MATCHER MCP  │  decision│ B. AUTOMATOR     │
│  (JobSpy)     │──────────▶│  (the brain)     │─────────▶│  (acts in world) │
│               │           │  • Master Profile│  +tailored│ • render docs    │
│ scrape boards │           │  • match & rank  │  content │ • submit forms   │
│ + career pages│◀──────────│  • tailor (LLM)  │◀─────────│ • send outreach  │
└───────────────┘  re-query └──────────────────┘  results └──────────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────┐
                         │   Shared Store (DB)       │
                         │  jobs · profile · apps ·  │
                         │  emails · run logs        │
                         └──────────────────────────┘
```

Three services, one shared data store, one orchestrator. The Matcher is an **MCP
server**, so any LLM agent (Claude Code included) can drive the whole thing by
calling its tools.

---

## 1. Tech stack (proposed)

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** | JobSpy is Python; richest scraping + LLM ecosystem |
| Job scraping | **JobSpy** (MIT) | Covers LinkedIn/Indeed/Glassdoor/Google/Naukri, surfaces emails |
| Career-page crawl | **Playwright** | Handles JS-heavy ATS pages (Greenhouse, Lever, Workday) |
| Form automation | **Playwright** | Same engine for apply-flow; reliable, headful-debuggable |
| LLM access | **LiteLLM** (gateway) | One API for Claude/GPT/Gemini/local → model & gateway agnostic |
| Matcher protocol | **MCP** (`mcp` Python SDK) | Exposes profile+match+tailor as tools any agent can call |
| Data store | **SQLite** (v1) → Postgres | Zero-setup start; clean migration path |
| Resume render | **Jinja2 + Chromium** (Playwright, HTML→PDF) | Full styling control, no GTK dependency; WeasyPrint optional fallback |
| Email | **Gmail API** / SMTP | Send from user's own mailbox |
| Config | **pydantic-settings** + `.env` | Typed config, secrets out of code |
| Orchestration | **Typer** CLI (v1) → optional FastAPI + web UI | Start scriptable, grow into a dashboard |

> All choices are defaults, not dogma. The contracts in §3 matter more than the
> libraries.

---

## 2. Repository layout

```
Intern_piperline/
├── VISION.md
├── ARCHITECTURE.md
├── ROADMAP.md
├── SETUP.md
├── aggregator-jobspy/        # A — JobSpy clone (MIT), used as a library
│
├── packages/
│   ├── common/               # shared schemas: JobPost, Profile, Application…
│   │   └── models.py         #   pydantic models = the contracts between parts
│   │
│   ├── aggregator/           # A — thin wrapper around JobSpy + career crawlers
│   │   ├── sources/          #   jobspy_source.py, greenhouse.py, lever.py…
│   │   └── service.py        #   discover(query) -> list[JobPost]
│   │
│   ├── matcher_mcp/          # C — the brain, an MCP server
│   │   ├── profile/          #   load/parse Master Profile, GitHub enrichment
│   │   ├── matching/         #   score + rank jobs vs profile
│   │   ├── tailoring/        #   LLM resume / cover-letter / email generation
│   │   └── server.py         #   MCP tool definitions
│   │
│   └── automator/            # B — acts in the world
│       ├── render/           #   profile+tailored text -> PDF/DOCX
│       ├── apply/            #   Playwright form-fill + submit
│       └── outreach/         #   email discovery + send
│
├── llm/                      # shared LLM gateway (LiteLLM wrapper, prompts)
├── orchestrator/             # CLI + pipeline runner + scheduler
├── data/
│   ├── profile/              # the user's Master Profile (yaml/json + assets)
│   └── piperline.db          # SQLite store
└── config/
    ├── .env.example
    └── settings.example.yaml
```

---

## 3. The contracts (shared schemas)

These three pydantic models are the spine. As long as they're stable, each part
can be rewritten freely.

### `JobPost` — produced by Aggregator, consumed by everyone
```python
class JobPost(BaseModel):
    id: str                 # stable hash(source + external_id) → dedup key
    source: str             # "linkedin" | "indeed" | "greenhouse" | ...
    title: str
    company: str
    location: str | None
    is_remote: bool | None
    job_type: str | None    # "internship" | "fulltime" | ...
    description: str         # full JD (markdown)
    url: str                 # apply / posting URL
    emails: list[str] = []   # contacts found in the posting (JobSpy gives these)
    salary: Salary | None
    date_posted: date | None
    raw: dict = {}           # source-specific extras
```

### `Profile` — the Master Profile, owned by Matcher MCP
```python
class Profile(BaseModel):
    basics: Basics              # name, email, phone, location, links
    summary: str
    education: list[Education]
    experience: list[Experience]
    projects: list[Project]     # title, impact, tech[], links
    achievements: list[str]
    skills: list[Skill]         # name + level + category
    links: dict[str, str]       # github, portfolio, linkedin
    # never mutated by tailoring — tailoring only SELECTS/REFRAMES from this
```

### `Application` — the unit of work, lives in the store
```python
class Application(BaseModel):
    id: str
    job_id: str                 # -> JobPost.id  (idempotency: one per job)
    status: Literal["discovered","scored","tailored","ready",
                    "applied","emailed","replied","skipped","error"]
    fit_score: float | None
    fit_rationale: str | None
    resume_path: str | None     # rendered artifact
    cover_letter_path: str | None
    outreach: Outreach | None    # contact, draft, sent_at, reply
    history: list[Event]         # full audit trail, makes runs resumable
```

---

## 4. Part A — Job Board Aggregator

**Job:** turn "I want backend internships, remote, posted this week" into a
deduped list of `JobPost`.

- `sources/jobspy_source.py` — wraps `jobspy.scrape_jobs(...)`, maps its
  DataFrame rows into our `JobPost`. Carries through the `emails` field (key for
  outreach) and uses `job_type="internship"`, `hours_old`, `is_remote`, `location`.
- `sources/{greenhouse,lever,ashby,workday}.py` — direct ATS crawlers (Playwright
  / public JSON endpoints) for company career pages JobSpy doesn't cover.
- `service.discover(query) -> list[JobPost]` — fan out to enabled sources
  concurrently, dedup by `JobPost.id`, persist to store.
- **Risk isolation:** all ToS-sensitive scraping lives here, behind rate limits,
  proxy rotation, and backoff on HTTP 429.

## 5. Part C — Job Matcher MCP (the brain)

**Job:** own the Master Profile, decide which jobs are worth it, and generate the
tailored content. Exposed as MCP tools so any agent can orchestrate it.

- `profile/loader.py` — load Master Profile from `data/profile/` (YAML/JSON),
  validate into `Profile`. `profile/github.py` — optional enrichment (repos,
  languages, README highlights) to en8rich projects/skills.
- `matching/scorer.py` — score a `JobPost` vs `Profile`: skill overlap, must-have
  keyword coverage, seniority/role fit, location/remote constraints. Hybrid:
  cheap deterministic signals + an LLM judgement for nuance. Returns
  `fit_score` + `fit_rationale`.
- `tailoring/` — LLM generation, all grounded in `Profile`:
  - `resume.py` — select & reorder real items to match the JD; output structured
    resume JSON (not freeform) so rendering stays consistent.
  - `cover_letter.py`, `outreach_email.py` — same grounding rule.
  - A **fabrication guard**: post-generation check that every claim maps to a
    Profile fact; flag/strip anything that doesn't.

### MCP tools exposed by `server.py`
| Tool | Input | Output |
|---|---|---|
| `get_profile` | — | the Master Profile |
| `match_job` | `JobPost` | `fit_score`, `fit_rationale` |
| `rank_jobs` | `JobPost[]` | sorted candidates above threshold |
| `tailor_resume` | `job_id` | structured resume + render-ready data |
| `draft_cover_letter` | `job_id` | cover letter text |
| `draft_outreach` | `job_id`, `contact` | personalized email draft |

## 6. Part B — Application Automator

**Job:** take the Matcher's decisions + content and act in the world.

- `render/` — `Profile` + tailored resume JSON → styled **PDF** (Jinja2 +
  WeasyPrint) and **DOCX** (`python-docx`). Multiple templates selectable.
- `apply/` — Playwright agent: open `JobPost.url`, detect the ATS, fill standard
  fields from `Profile`, upload rendered resume/cover letter, answer screening
  questions from Profile. **Escalates** CAPTCHAs / paid assessments / ambiguous
  questions to a human-review queue instead of guessing.
- `outreach/` — email discovery (posting emails → company-domain pattern guess →
  optional enrichment API → verify) then send via Gmail API/SMTP from the user's
  mailbox. Default: write to the **approval queue**; autopilot sends directly.

## 7. Shared LLM gateway (`llm/`)

One thin module wrapping **LiteLLM** so the rest of the code calls
`llm.complete(messages, model=...)` and never knows the provider. Model + gateway
chosen in config (`gpt-4o`, `claude-...`, `gemini-...`, local). Centralizes
retries, token budgeting, prompt templates, and caching. This is what makes the
system "any AI model, any gateway" per the vision.

## 8. Orchestrator & control flow

`orchestrator/pipeline.py` runs the loop and is **resumable + idempotent**:

```
discover → for each new JobPost:
  match_job → if score < threshold: status=skipped
            → else: tailor_resume + draft_cover_letter → render → status=ready
                    discover contact + draft_outreach → status=ready
review gate (default ON):
  human approves queue  ── or ── stage is on autopilot
on approval:
  apply (submit form) → status=applied
  send outreach        → status=emailed
track replies → status=replied
```

Every transition writes an `Event` to `Application.history`, so a crash resumes
exactly where it stopped and the same job is never applied to twice.

## 9. Security & secrets

- All keys (LLM, email, enrichment) in `.env` / OS keychain — never in code or
  the DB. `config/.env.example` documents every variable.
- The user's resume/profile data stays local (SQLite + `data/`).
- Outbound email uses the user's own authenticated mailbox; no third-party relay
  sees application content unless the user configures one.

---

*Next: `ROADMAP.md` sequences this into shippable milestones.*
