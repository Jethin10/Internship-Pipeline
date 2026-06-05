"""The pipeline runner — discover -> score -> tailor -> render -> ready -> apply -> outreach.

Full automation mode (autopilot): when settings.autopilot_apply and/or
settings.autopilot_outreach are true, the pipeline continues past `ready` to
actually submit applications and send outreach emails. Safety gates still apply:
CAPTCHAs escalate, rate limits enforced, suppression list honored.

Properties:
  - Idempotent: a job already past a stage is not reprocessed.
  - Resumable: every status change appends an Event, so a crashed run picks up
    from the last persisted state.
  - Degrades gracefully: with no LLM key, scoring falls back to deterministic and
    tailoring is skipped (applications stop at `scored`).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from piperline.aggregator import DiscoverQuery, discover
from piperline.common import Application, JobPost
from piperline.config import DATA_DIR, Settings, get_settings
from piperline.store import Store, advance


@dataclass
class RunStats:
    discovered: int = 0
    new_jobs: int = 0
    scored: int = 0
    skipped: int = 0
    tailored: int = 0
    ready: int = 0
    applied: int = 0
    apply_escalated: int = 0
    emailed: int = 0
    email_blocked: int = 0
    errors: int = 0

    def summary(self) -> str:
        parts = [
            f"discovered={self.discovered}",
            f"new={self.new_jobs}",
            f"scored={self.scored}",
            f"skipped={self.skipped}",
            f"tailored={self.tailored}",
            f"ready={self.ready}",
        ]
        if self.applied or self.apply_escalated:
            parts.append(f"applied={self.applied}")
            if self.apply_escalated:
                parts.append(f"escalated={self.apply_escalated}")
        if self.emailed or self.email_blocked:
            parts.append(f"emailed={self.emailed}")
            if self.email_blocked:
                parts.append(f"blocked={self.email_blocked}")
        parts.append(f"errors={self.errors}")
        return " ".join(parts)


def _app_id(job_id: str) -> str:
    return f"app-{job_id}"


def run_pipeline(
    query: DiscoverQuery,
    *,
    settings: Settings | None = None,
    use_llm: bool = True,
    autopilot: bool = False,  # when True, respects autopilot_apply/outreach flags
    on_event=None,  # optional callback(str) for progress
) -> RunStats:
    """Run discovery + scoring + tailoring, and optionally apply + outreach.

    With autopilot=True, continues past 'ready' to submit applications and send
    outreach emails IF the corresponding settings flags are enabled. Without
    autopilot=True, stops at 'ready' regardless of settings (safe default).
    """
    settings = settings or get_settings()
    store = Store(settings.db_path)
    stats = RunStats()
    log = on_event or (lambda _msg: None)

    # 1. DISCOVER
    posts = discover(query, settings=settings)
    stats.discovered = len(posts)
    log(f"discovered {len(posts)} postings")

    profile = _load_profile_or_none(log)
    if profile is None:
        return stats

    for job in posts:
        is_new = store.upsert_job(job)
        if is_new:
            stats.new_jobs += 1
        # idempotency: skip anything already processed past 'discovered'
        existing = store.get_application(job.id)
        if existing and existing.status not in ("discovered", "error"):
            # But if autopilot is on, we may need to continue from 'ready'
            if autopilot and existing.status == "ready":
                try:
                    _process_autopilot(job, existing, profile, store, stats, settings, log)
                except Exception as e:
                    advance(existing, "error", f"{type(e).__name__}: {e}")
                    store.save_application(existing)
                    stats.errors += 1
                    log(f"[error] {job.title}: {e}")
            continue
        app = existing or advance(Application(id=_app_id(job.id), job_id=job.id), "discovered")
        try:
            _process_one(job, app, profile, store, stats, settings, use_llm, autopilot, log)
        except Exception as e:  # never let one job kill the run
            advance(app, "error", f"{type(e).__name__}: {e}")
            store.save_application(app)
            stats.errors += 1
            log(f"[error] {job.title}: {e}")

    return stats


def _process_one(job, app, profile, store, stats, settings, use_llm, autopilot, log) -> None:
    from piperline.matcher.scorer import score_job

    # 2. SCORE
    fit = score_job(job, profile, settings=settings, use_llm=use_llm)
    app.fit_score = fit.score
    app.fit_rationale = fit.rationale
    advance(app, "scored", f"score={fit.score}")
    store.save_application(app)
    stats.scored += 1

    # Threshold is mode-aware: deterministic-only scores run lower, so they use
    # a gentler cutoff (see config). This keeps preview runs (no LLM key) useful.
    threshold = settings.fit_threshold if use_llm else settings.deterministic_fit_threshold
    if fit.score < threshold:
        advance(app, "skipped", f"below threshold {threshold}")
        store.save_application(app)
        stats.skipped += 1
        log(f"[skip {fit.score}] {job.title} @ {job.company}")
        return

    if not use_llm:
        log(f"[scored {fit.score}] {job.title} (LLM off — not tailoring)")
        return

    # 3. TAILOR + guard
    from piperline.matcher.tailor import tailor_resume

    result = tailor_resume(job, profile, settings=settings)
    note = "guard ok" if result.guard.ok else f"guard flags: {len(result.guard.flags)}"
    advance(app, "tailored", note)
    store.save_application(app)
    stats.tailored += 1

    # 4. RENDER resume + cover letter
    from piperline.matcher.letters import draft_cover_letter
    from piperline.render import render_resume_pdf

    out_dir = DATA_DIR / "output" / job.id
    pdf = out_dir / "resume.pdf"
    try:
        render_resume_pdf(result.profile, pdf)
        app.resume_path = str(pdf)
    except RuntimeError:
        app.resume_path = str(pdf.with_suffix(".html"))  # HTML fallback still written

    letter = draft_cover_letter(job, profile, settings=settings)
    cl = out_dir / "cover_letter.txt"
    cl.parent.mkdir(parents=True, exist_ok=True)
    cl.write_text(letter, encoding="utf-8")
    app.cover_letter_path = str(cl)

    # 5. OUTREACH — find a hiring contact (no LLM) + draft a message (LLM).
    #    Stored on the application; NOT sent (sending is gated, later milestone).
    _attach_outreach(job, profile, app, settings, log)

    advance(app, "ready", "resume + cover letter + outreach draft prepared")
    store.save_application(app)
    stats.ready += 1
    log(f"[ready {app.fit_score}] {job.title} @ {job.company}")

    # 6. AUTOPILOT — apply and/or send outreach if enabled
    if autopilot:
        _process_autopilot(job, app, profile, store, stats, settings, log)


def _process_autopilot(job, app, profile, store, stats, settings, log) -> None:
    """World-acting stages, gated by settings. Called only when autopilot=True.

    Each stage is independently gated by its own settings flag and fails soft:
    an apply failure never blocks outreach, and neither aborts the run.
    """
    # 7. AUTO-APPLY — submit the form if autopilot_apply is on.
    if settings.autopilot_apply and app.status == "ready":
        _auto_apply(job, app, profile, store, stats, settings, log)

    # 8. AUTO-OUTREACH — send the drafted email if autopilot_outreach is on.
    if settings.autopilot_outreach:
        _auto_outreach(job, app, profile, store, stats, settings, log)


def _auto_apply(job, app, profile, store, stats, settings, log) -> None:
    from piperline.automator import fill_application

    if not job.url:
        log(f"[apply skip] {job.title}: no apply URL")
        return

    out_dir = DATA_DIR / "output" / job.id
    res = fill_application(
        job.url, profile, settings=settings,
        resume_path=app.resume_path, cover_letter_path=app.cover_letter_path,
        screenshot_dir=out_dir, submit=True, headless=True,
        interactive=False,  # autopilot = unattended, can't pause for CAPTCHAs
    )
    if res.submitted:
        advance(app, "applied", f"auto-submitted via {res.ats}")
        store.save_application(app)
        stats.applied += 1
        log(f"[applied] {job.title} @ {job.company}")
    elif res.escalations:
        # Record the escalation in history but leave status at 'ready' for a human.
        advance(app, "ready", f"apply escalated: {'; '.join(res.escalations)}")
        store.save_application(app)
        stats.apply_escalated += 1
        log(f"[apply needs you] {job.title}: {'; '.join(res.escalations)}")
    elif res.error:
        log(f"[apply error] {job.title}: {res.error}")


def _auto_outreach(job, app, profile, store, stats, settings, log) -> None:
    from datetime import datetime

    from piperline.outreach.sender import send_email

    o = app.outreach
    if not (o and o.contact_email and o.subject and o.body):
        return
    if o.sent_at is not None:  # idempotency: never email the same contact twice
        return

    # Gather profile links for the email
    linkedin_url = None
    github_url = None
    if profile.links:
        linkedin_url = profile.links.get("linkedin") if isinstance(profile.links, dict) else getattr(profile.links, "linkedin", None)
        github_url = profile.links.get("github") if isinstance(profile.links, dict) else getattr(profile.links, "github", None)

    res = send_email(
        o.contact_email, o.subject, o.body,
        settings=settings, send=True,
        resume_path=app.resume_path,
        linkedin_url=linkedin_url,
        github_url=github_url,
    )
    if res.sent:
        o.sent_at = datetime.now()
        # Only advance to 'emailed' if not already applied (applied is further along).
        if app.status != "applied":
            advance(app, "emailed", f"auto-sent to {o.contact_email}")
        else:
            app.history.append(_event("emailed", f"auto-sent to {o.contact_email}"))
        store.save_application(app)
        stats.emailed += 1
        log(f"[emailed] {job.title} -> {o.contact_email}")
    elif res.blocked_reason:
        stats.email_blocked += 1
        log(f"[email blocked] {job.title}: {res.blocked_reason}")
    elif res.error:
        log(f"[email error] {job.title}: {res.error}")


def _event(status, note):
    from datetime import datetime

    from piperline.common import Event

    return Event(at=datetime.now(), status=status, note=note)


def _attach_outreach(job, profile, app, settings, log) -> None:
    """Discover a contact and draft a personalized outreach email (best-effort)."""
    from piperline.common import Outreach
    from piperline.outreach import best_contact

    contact = best_contact(job)
    outreach = Outreach(
        contact_email=contact.email if contact else None,
        contact_name=contact.name if contact else None,
        contact_source=contact.source if contact else None,
    )
    try:
        from piperline.matcher.letters import draft_outreach

        draft = draft_outreach(
            job, profile, settings=settings,
            contact_name=contact.name if contact else None,
        )
        outreach.subject = draft.subject
        outreach.body = draft.body
    except Exception as e:
        log(f"[outreach draft skipped] {type(e).__name__}")
    app.outreach = outreach


def _load_profile_or_none(log):
    from piperline.matcher import load_profile

    try:
        return load_profile()
    except FileNotFoundError as e:
        log(f"[fatal] {e}")
        return None
