# Internship Pipeline

An autonomous job/internship application engine. It discovers openings, learns
your profile, tailors a resume + cover letter to each opening, applies on your
behalf, and sends a personalized note to the hiring contact — at scale, with
you in control.

> **Read [VISION.md](./VISION.md)** for why this exists,
> **[ARCHITECTURE.md](./ARCHITECTURE.md)** for the design,
> **[ROADMAP.md](./ROADMAP.md)** for what's built and what's next.

---

## Quick Start

### 1. Prerequisites

- **Python 3.10+** (tested on 3.13)
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- An **LLM API key** — any of:
  - [Anthropic](https://console.anthropic.com/) (Claude)
  - [OpenAI](https://platform.openai.com/) (GPT-4o)
  - [Google AI](https://aistudio.google.com/) (Gemini)
  - [OpenRouter](https://openrouter.ai/) (multi-provider gateway, free models available)
  - Or any provider compatible with LiteLLM

### 2. Install

```bash
# Clone
git clone https://github.com/Jethin10/Internship-Pipeline.git
cd Internship-Pipeline

# Create venv + install (uv — recommended)
uv venv
uv pip install -e .

# Or with standard pip
python -m venv .venv
.venv/Scripts/pip install -e .      # Windows
# source .venv/bin/pip install -e .   # macOS/Linux

# Install Playwright browsers (needed for rendering + apply)
.venv/Scripts/playwright install chromium   # Windows
# .venv/bin/playwright install chromium      # macOS/Linux
```

### 3. Configure

```bash
# Copy the env template and fill in your keys
cp config/.env.example config/.env
```

Edit `config/.env` — the minimum you need:

```env
# Pick your LLM provider. Examples:

# Option A: OpenRouter (easiest — has free models, no custom base URL needed)
LLM_MODEL=openrouter/moonshotai/kimi-k2.6:free
LLM_API_KEY=sk-or-v1-your-key-here
LLM_API_BASE=https://openrouter.ai/api/v1

# Option B: Anthropic Claude
# LLM_MODEL=claude-opus-4-8
# LLM_API_KEY=sk-ant-...

# Option C: OpenAI
# LLM_MODEL=gpt-4o
# LLM_API_KEY=sk-...
```

Then **create your profile**:

```bash
cp data/profile/profile.example.yaml data/profile/profile.yaml
```

Edit `data/profile/profile.yaml` with your real details: name, education,
experience, projects, skills. This is the *single source of truth* — every
resume, cover letter, and outreach email is derived from it.

### 4. Verify It Works

```bash
# Check your profile loads cleanly
piperline profile-check

# Render a baseline resume from your profile
piperline render-resume
# → data/output/resume.pdf
```

### 5. Discover & Tailor (Read-Only)

```bash
# Search for openings
piperline discover-jobs "machine learning intern" -l "Remote" --internship --hours 72 -n 15

# Run the full read-only pipeline: discover → score → tailor → render
piperline run "software engineering intern" -l "New York" --internship

# See your funnel
piperline dashboard
piperline status
```

### 6. Tailor for a Specific Job

```bash
# Paste a job description into a text file, then:
piperline tailor sample_jd.txt --title "ML Engineer Intern" --company "Acme Corp"
# → data/output/tailored.pdf  +  tailored_cover_letter.txt
```

---

## Commands

| Command | What it does |
|---|---|
| `piperline discover-jobs "query"` | Search job boards (LinkedIn, Indeed, Glassdoor, Google) |
| `piperline profile-check` | Load + validate your Master Profile |
| `piperline render-resume` | Render your profile → PDF resume |
| `piperline tailor jd.txt --title "..."` | Score a JD + tailor your resume + cover letter |
| `piperline run "query"` | Full read-only pipeline: discover → score → tailor → render |
| `piperline autopilot "query"` | Full autonomous loop: discover → score → tailor → apply → email |
| `piperline status` | See your application queue |
| `piperline dashboard` | Funnel view: conversion rates + activity feed |
| `piperline apply <job-id>` | Fill an application form (screenshot, no submit by default) |
| `piperline outreach` | Review outreach queue (contacts + drafts) |
| `piperline send-outreach` | Send queued outreach emails (dry-run by default) |
| `piperline analyze-github <user>` | Inspect any GitHub user's repos |
| `piperline enrich-profile <user>` | Generate profile suggestions from GitHub |

---

## Safety: Autopilot & Guardrails

By default, the pipeline is **read-only** — it discovers, scores, and tailors,
but **never submits applications or sends emails**. That's intentional.

To enable autopilot (world-acting mode), set these in `config/.env`:

```env
AUTOPILOT_APPLY=true         # auto-submit application forms
AUTOPILOT_OUTREACH=true      # auto-send outreach emails
```

Even with autopilot on:

- **CAPTCHAs** escalate to human review (left at `ready`)
- **Unmapped form fields** escalate to human review
- **Outreach** respects a daily rate cap (`MAX_OUTREACH_PER_DAY=20`)
- **Outreach** is idempotent — never emails the same contact twice
- **The fabrication guard** strips any resume claim not in your profile
- Each stage can be independently toggled off

For cold email: the system sends low-volume, individually personalized messages
from **your own SMTP mailbox**. It's not a spam tool — it's designed for
responsible, targeted outreach.

---

## Config Reference

All settings live in `config/.env`:

| Variable | Default | Notes |
|---|---|---|
| `LLM_MODEL` | `claude-opus-4-8` | LiteLLM model name: `claude-...`, `gpt-4o`, `gemini/gemini-...`, `openrouter/...` |
| `LLM_API_KEY` | — | Your API key |
| `LLM_API_BASE` | — | Custom gateway endpoint (leave blank for direct provider) |
| `LLM_TEMPERATURE` | `0.4` | 0.0–2.0 |
| `FIT_THRESHOLD` | `0.6` | Blended (LLM) score cutoff for matches |
| `DETERMINISTIC_FIT_THRESHOLD` | `0.25` | Cutoff when running `--no-llm` (cheaper prefilter) |
| `AUTOPILOT_APPLY` | `false` | Auto-submit application forms |
| `AUTOPILOT_OUTREACH` | `false` | Auto-send outreach emails |
| `MAX_OUTREACH_PER_DAY` | `20` | Daily email cap |
| `SMTP_HOST` | — | e.g. `smtp.gmail.com` |
| `SMTP_PORT` | `587` | — |
| `SMTP_USER` | — | Your email (for Gmail, use an [app password](https://myaccount.google.com/apppasswords)) |
| `SMTP_PASS` | — | App password |
| `DEFAULT_COUNTRY_INDEED` | `usa` | Country for Indeed searches |

---

## MCP Server (Optional)

The pipeline can run as an MCP server, exposing profile/match/tailor/outreach
as tools any MCP client (Claude Desktop, Claude Code) can call.

See **[MCP_SETUP.md](./MCP_SETUP.md)** for setup instructions.

---

## Architecture

```
                        ┌──────────────────────────┐
                        │     Orchestrator / CLI    │
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
└───────────────┘           │  • tailor (LLM)  │◀─────────│ • send outreach  │
                            └──────────────────┘  results └──────────────────┘
```

Three parts, one store, one orchestrator. Read the full design in
**[ARCHITECTURE.md](./ARCHITECTURE.md)**.

---

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.10+ |
| Job scraping | [JobSpy](https://github.com/speedyapply/JobSpy) (MIT) |
| Form automation | Playwright + playwright-stealth |
| LLM access | [LiteLLM](https://github.com/BerriAI/litellm) — model & gateway agnostic |
| Data store | SQLite |
| Resume render | Jinja2 → HTML → Chromium PDF |
| Email | SMTP (Gmail or any provider) |
| Config | pydantic-settings + .env |

---

## License

MIT — see [LICENSE](./LICENSE).

---

*Built with feedback from Claude Code.*
