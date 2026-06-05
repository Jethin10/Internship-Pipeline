# VISION.md — Intern Piperline

> An autonomous job/internship application engine. It finds openings, understands
> *you* deeply, tailors a resume + cover letter to each opening, applies on your
> behalf, and reaches out to the right human with a personalized note — at scale,
> while keeping you in control.

---

## 1. The one-sentence vision

**Stop applying to jobs one by one. Describe yourself once, and let an AI agent
find every relevant opening, write a custom resume for each, apply, and email the
hiring contact a personal message — so you wake up to interviews, not to a backlog
of applications.**

---

## 2. Who this is for

- A student / new-grad / early-career engineer hunting internships and entry roles.
- Someone who has *real* projects, achievements, and skills, but no time to
  hand-tailor 50 resumes a week.
- Anyone who believes a generic resume blasted everywhere is worse than a
  targeted resume sent to the right 30 openings with a personal note.

The primary user is the project owner (a single person, "me"). Multi-user / SaaS
is a possible future, not the v1 goal.

---

## 3. The problem we are solving

Job hunting today is broken in three specific ways:

1. **Discovery is fragmented.** Openings are scattered across LinkedIn, Indeed,
   Glassdoor, Google Jobs, Naukri, and thousands of company career pages. No one
   sees them all.
2. **Tailoring doesn't scale.** A resume tuned to the job description gets far more
   callbacks, but hand-tailoring is slow, so people send the same generic PDF
   everywhere and convert poorly.
3. **The application itself is dead air.** Submitting a form into an ATS black hole
   gets ignored. A short, genuine, *personalized* message to an actual human
   (recruiter / hiring manager / founder) is what actually gets replies — but
   finding that contact and writing 50 different notes is exhausting.

Intern Piperline attacks all three at once.

---

## 4. The end-to-end flow (the heart of the project)

```
        ┌─────────────────────────────────────────────────────────────┐
        │                     INTERN PIPERLINE                          │
        └─────────────────────────────────────────────────────────────┘

  [1] DISCOVER            [2] UNDERSTAND ME        [3] MATCH & RANK
  ───────────            ──────────────────        ────────────────
  Crawl job boards   →   Parse my knowledge   →    Score every job vs my
  (LinkedIn, Indeed,     base: projects,           profile. Keep the ones
  Glassdoor, Google,     achievements, skills,     worth applying to. Drop
  Naukri, career         GitHub, portfolio,        the noise. Rank by fit.
  pages). Normalize      past roles. Build a
  every posting into     structured "Master
  one schema.            Profile".

         │                                                  │
         ▼                                                  ▼

  [4] TAILOR                                  [5] APPLY
  ─────────                                   ─────────
  For each kept job, an LLM writes:           Auto-fill & submit the
   • a resume rewritten to mirror the JD      application: web forms,
     (real content only — never fabricated)   file uploads, screening
   • a matching cover letter                  questions. Pause for
   • a one-page "why I fit" rationale         human review when needed.

                          │
                          ▼

  [6] REACH OUT                               [7] TRACK & LEARN
  ────────────                                ────────────────
  Find the hiring contact's email             Log every application,
  (from the posting, company domain,          email, and reply in one
  enrichment). Write a short, personal        dashboard. Learn which
  message tied to THIS opening and MY         resume/message variants
  background. Send (or queue for approval).   convert, and improve.
```

### Step-by-step detail

**[1] Discover** — Aggregate openings from major job boards via a scraping engine
(JobSpy as the base) plus direct company-careers crawlers. Filter by role,
location, remote, "internship" type, and freshness (e.g. posted in last 72h).
Output: a normalized stream of `JobPost` records (title, company, JD, URL,
location, salary, *and any emails found in the posting*).

**[2] Understand me** — Parse a personal knowledge base into one structured
**Master Profile**: education, projects (with impact + tech), achievements,
skills, work/volunteer history, links (GitHub, portfolio, LinkedIn). Optionally
enrich from GitHub (repos, languages, READMEs) and a portfolio site. This is the
*single source of truth* — every tailored document is derived from it, and the
system must never invent facts not present here.

**[3] Match & rank** — For each job, compute a fit score from the JD against the
Master Profile (skills overlap, seniority fit, must-have keywords, location/remote
constraints). Above a threshold → candidate. Below → discard. Rank candidates so
the best-fit, highest-value openings get applied to first.

**[4] Tailor** — For each candidate job, an LLM (model-agnostic — see §6) produces:
- A **resume** reordered/reworded to surface the experiences and keywords the JD
  cares about. Grounded strictly in the Master Profile.
- A **cover letter** that connects my real background to this specific role/company.
- A short internal **fit rationale** (used for ranking + the outreach email).
Rendered to clean PDF (and DOCX) via a templating layer.

**[5] Apply** — A browser-automation agent fills and submits the application:
standard fields (name, email, links), resume/cover-letter uploads, and
free-text/EEO/screening questions answered from the Master Profile. Hard or
ambiguous steps (CAPTCHAs, unusual questions, paid assessments) are escalated to
the human instead of guessed.

**[6] Reach out** — Find the right human's email: first from the posting itself
(JobSpy surfaces `emails`), then from the company domain + name patterns, then
optional enrichment APIs. Draft a *short* (4–6 sentence) personalized message:
references the specific opening, names one concrete reason I fit, links my
portfolio, asks for a brief conversation. Send via the user's mailbox (Gmail /
SMTP) — by default queued for one-click approval, optionally fully automatic.

**[7] Track & learn** — Everything lands in one store + dashboard: which jobs were
found, scored, applied to, emailed; what got opened/replied. Over time, learn
which resume framings and message styles convert, and feed that back into [4]/[6].

---

## 5. Architecture: three cooperating parts

Mirrors the original ApplyStream AI split, kept as three decoupled services so
each can be developed, scaled, and replaced independently.

| Part | Name here | Responsibility | Base |
|------|-----------|----------------|------|
| **A** | **Job Board Aggregator** | Discover + normalize openings (steps 1) | `JobSpy` (MIT) |
| **B** | **Application Automator** | Tailor docs + submit forms + send outreach (steps 4–6) | Built fresh |
| **C** | **Job Matcher MCP** | Master Profile + matching/ranking, exposed as MCP tools (steps 2–3) | Built fresh (MCP) |

The **Matcher MCP** is the brain: it owns the Master Profile and the fit logic,
and exposes them as Model Context Protocol tools so any LLM client (Claude,
Claude Code, or a custom agent) can call `match_job`, `get_profile`,
`tailor_resume`, etc. The Aggregator feeds it jobs; the Automator consumes its
decisions and tailored content to act in the world.

See `ARCHITECTURE.md` for the technical design and data contracts.

---

## 6. Design principles (non-negotiables)

1. **Model-agnostic & gateway-agnostic.** Any LLM (Claude, GPT, Gemini, local)
   behind any gateway. One provider interface; swap via config, no code changes.
2. **Truthful by construction.** Tailoring *reframes* real facts from the Master
   Profile. It must never fabricate experience, skills, employers, or dates. A
   fabricated resume is a bug, not a feature.
3. **Human-in-the-loop by default.** Auto-draft everything; auto-*send* only what
   the user has explicitly switched to autopilot. Outreach emails especially
   default to review-then-send. (See §7.)
4. **One Master Profile, many derivations.** All documents trace back to a single
   structured profile. No facts live only inside a generated resume.
5. **Decoupled services, clean contracts.** Aggregator, Automator, and Matcher
   talk through stable schemas (a shared `JobPost` and `Profile` shape), so any
   one can be rewritten without breaking the others.
6. **Observable & resumable.** Every run is logged, every application is
   idempotent (never apply twice to the same job), and a crashed run resumes.

---

## 7. Guardrails: doing this responsibly (read this)

This system is powerful, and a few parts carry real risk. The vision explicitly
chooses the safe, durable version of each:

- **Terms of Service.** LinkedIn/Indeed actively prohibit scraping and bulk
  automation and ban accounts that do it. We isolate that risk in the Aggregator
  (rate-limited, proxy-aware, respects robots where applicable) and prefer
  official APIs / company career pages where available. Automated *submission*
  uses the user's own accounts and human-paced behavior.
- **Cold email & spam law.** Bulk unsolicited email is regulated (CAN-SPAM, GDPR,
  CASL). Outreach is **low-volume, individually personalized, and opt-out-aware**,
  sent from the user's own mailbox — not a blast. Default is *draft → human
  approves → send*.
- **No fabrication.** Enforced at the data layer (principle #2).
- **Autopilot is a deliberate switch.** Full hands-off apply+email is supported
  but **off by default**, per-stage, so the user consciously opts into it.

These aren't blockers — they're the difference between a tool that gets the user
banned and one that actually lands interviews and keeps working for years.

---

## 8. What "done" looks like (success criteria)

- I fill in my Master Profile once and connect my accounts/keys.
- I run one command (or hit one button) and the system surfaces a ranked list of
  fresh, relevant openings with a tailored resume + cover letter + draft outreach
  email already prepared for each.
- I review a queue and approve in bulk; approved items are applied + emailed
  automatically.
- I can flip individual stages to full autopilot once I trust them.
- A dashboard shows what was applied to, who was contacted, and what replied.
- Switching the underlying AI model or provider is a one-line config change.

---

## 9. Non-goals (for now)

- Not a multi-tenant SaaS (single-user first; SaaS is a later maybe).
- Not a tool to mass-spam recruiters (explicitly designed against this).
- Not a resume-fabrication tool.
- Not trying to defeat CAPTCHAs or impersonate the user dishonestly.

---

*This document is the north star. `ARCHITECTURE.md` is how we build it,
`ROADMAP.md` is the order we build it in.*
