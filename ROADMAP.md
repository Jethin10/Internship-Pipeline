# ROADMAP.md — Intern Piperline

The order we build it in. Each milestone is shippable and usable on its own — you
get value before the whole system exists. Build the spine first (profile → match →
render), then discovery, then the risky world-acting parts last and behind guards.

---

## Guiding sequencing principle

Build **inside-out**: the brain (Matcher) and your data (Profile) first, because
everything else depends on them. Add discovery (Aggregator) next so there's real
input. Do the world-acting parts (apply, email) *last* and *behind a human review
gate*, because they carry the ToS/spam risk and benefit most from the rest being
solid.

---

## Milestone 0 — Foundations  *(scaffolding)*  ✅ DONE
- [x] Repo layout per `ARCHITECTURE.md §2`; Python env (uv, py3.13).
- [x] `piperline/common/`: `JobPost`, `Profile`, `Application` (the contracts).
- [x] Typed settings (pydantic-settings); `config/.env.example`.
- [x] `llm/` gateway over LiteLLM (model/gateway-agnostic).
- *(DB store deferred to M5 — not needed until the pipeline persists state.)*

## Milestone 1 — Master Profile  *(understand me)*  ✅ DONE
- [x] Profile schema + `data/profile/profile.yaml` (copy `profile.example.yaml` and fill in your details).
- [x] Loader + validation; `profile-check` CLI.
- [x] GitHub learning: `matcher/github.py` (repos+READMEs) + `enrich.py` (LLM
      synthesis → suggested profile fragments). `analyze-github` / `enrich-profile`.
- *(LinkedIn: not auto-fetchable — 404 to scraping. Imported via user paste.)*

## Milestone 2 — Resume rendering  *(tangible output early)*  ✅ DONE
- [x] Jinja2 `resume.html.j2` template → HTML, then PDF.
- [x] **Headless Chromium (Playwright) as the PDF engine** (WeasyPrint needs GTK
      on Windows; Chromium is reliable + already needed for M7). `render-resume` CLI.
- [x] Real resume PDF renders from the Master Profile.

## Milestone 3 — Matcher core  *(the brain)*  ✅ DONE
- [x] `matching/scorer.py`: deterministic skill/keyword overlap + LLM nuance, blended.
- [x] `tailoring/tailor.py`: JD-tailored structured resume, grounded in Profile.
- [x] **Fabrication guard**: flags any org/role/project/skill/achievement not in
      the source profile (tested — catches fakes, passes clean subsets).
- [x] `letters.py`: cover letter + short outreach email drafts.
- [x] `tailor` CLI: score → tailor → guard → render PDF → cover letter.
- [ ] Expose as MCP tools (`server.py`) — deferred; CLI-first for now.

## Milestone 4 — Aggregator  *(discover, real input)*  ✅ DONE (core)
- [ ] `sources/jobspy_source.py`: JobSpy → `JobPost` (carry `emails`, internship
      filter, `hours_old`, remote, location).
- [ ] `service.discover()`: concurrent fan-out, dedup, persist; rate-limit/backoff.
- [ ] (Stretch) one ATS career-page crawler (Greenhouse or Lever) via Playwright.
- **Done when:** one query returns deduped fresh `JobPost`s in the store.

## Milestone 5 — Pipeline (read-only)  *(the loop, no world-acting yet)*  ✅ DONE
- [x] SQLite store (`store.py`): JobPost + Application as JSON rows, idempotent
      upsert keyed by stable id, status/funnel queries.
- [x] `orchestrator/pipeline.py`: discover → score → tailor → render → `ready`.
- [x] Idempotency (never reprocess) + resumability via `Application.history`.
- [x] Mode-aware threshold (0.6 blended / 0.25 deterministic preview).
- [x] CLI: `run "..."` and `status`. **Verified live** on 8 real Indeed ML
      internships; idempotent re-run reprocessed 0.

## Milestone 6 — Outreach drafting + email discovery  *(still no auto-send)*  ✅ DONE
- [x] Contact discovery (`outreach/discovery.py`): posting emails (0.9 conf) →
      company-domain role addresses (careers@/jobs@/hr@) with **MX verification**
      (dnspython). Responsible: no personal-email brute-forcing.
- [x] `matcher/letters.py`: short personalized outreach draft per opening.
- [x] Pipeline attaches contact + draft to `Application.outreach` at `ready`.
- [x] `outreach` CLI = approve-only review queue; **nothing is sent**.
- [x] Verified live: found real posting emails + verified role addresses on the
      8 stored Indeed jobs.

## Milestone 7 — Auto-apply (guarded)  *(world-acting, behind the gate)*  ✅ DONE
- [x] `automator/ats.py`: detect Greenhouse/Lever/Workday/Ashby/generic from URL,
      field-mapping registry per ATS.
- [x] `automator/answers.py`: answer screening questions from Profile via LLM,
      with confidence + escalation for sensitive/legal questions (sponsorship,
      salary, demographics).
- [x] `automator/apply.py`: Playwright fills form, uploads docs, screenshots.
      **Submit only if autopilot_apply=true AND submit=True AND no escalations.**
      CAPTCHAs escalate. Verified: fills local test form, does NOT submit by
      default (safety gate proven).
- [x] `apply` CLI command.

## Milestone 8 — Auto-send outreach (guarded)  ✅ DONE
- [x] `outreach/sender.py`: SMTP send from user mailbox, **dry-run default**,
      daily rate cap (max_outreach_per_day), suppression list (opt-outs).
      Real send needs autopilot_outreach=true AND --send.
- [x] `send-outreach` CLI command. Verified: suppression blocks, dry-run is
      default, rate cap enforced.

## MCP Server  ✅ DONE
- [x] `matcher_mcp/server.py`: exposes get_profile, match_job, tailor_resume,
      draft_cover_letter, draft_outreach as MCP tools. Verified: imports + structure valid.

## Milestone 9 — Track & learn  ✅ DONE (dashboard + funnel)
- [x] Dashboard (`dashboard` CLI): ordered funnel discovered→scored→tailored→
      ready→applied→emailed→replied, per-stage counts + bars + conversion rates,
      side-branches (skipped/error), and a recent-activity feed.
      `orchestrator/dashboard.py` computes the funnel from `Application.history`
      (high-water mark, not just current status, so applied+emailed both count).
- [x] **Full automation wired**: `autopilot` CLI runs discover→…→ready→APPLY→
      EMAIL in one loop, gated by AUTOPILOT_APPLY / AUTOPILOT_OUTREACH. Apply
      escalations (CAPTCHA/unmapped) leave the app at `ready` for a human;
      outreach is idempotent (never re-emails) and respects cap+suppression.
- [ ] Reply detection; conversion stats per resume/message variant (future).
- [ ] Feedback into matching/tailoring prompts (future).
- **Done when:** one view shows the full funnel. ✅ `piperline dashboard`

---

## Risk register (track alongside milestones)

| Risk | Where | Mitigation | Milestone |
|---|---|---|---|
| Job-board ToS / IP bans | Aggregator | rate limit, proxies, prefer APIs/career pages | 4 |
| Spam law (CAN-SPAM/GDPR) | Outreach | low-volume, personalized, opt-out, user mailbox | 6,8 |
| Resume fabrication | Tailoring | fabrication guard, Profile-grounded only | 3 |
| Silent wrong auto-apply | Apply | human gate default-on, escalate hard cases | 7 |
| Key leakage | All | .env/keychain, never in DB/code | 0 |

## Suggested first sprint
**M0 + M1 + M2** — scaffolding, your real Master Profile, and a rendered baseline
resume. Fastest path to something real in your hands, and it unblocks everything
after it.
