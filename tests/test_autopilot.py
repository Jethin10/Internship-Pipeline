"""Autopilot + dashboard tests — gating logic and funnel math, no network/LLM."""
import gc
from datetime import datetime
from pathlib import Path

from piperline.common import Application, Event, JobPost, Outreach
from piperline.orchestrator.dashboard import build_funnel, recent_activity
from piperline.orchestrator.pipeline import (
    RunStats,
    _app_id,
    _auto_apply,
    _auto_outreach,
)
from piperline.store import Store, advance


class _Settings:
    autopilot_apply = True
    autopilot_outreach = True
    max_outreach_per_day = 20
    smtp_host = smtp_user = smtp_pass = None
    smtp_port = 587


def _store(tmp_path: Path) -> Store:
    return Store(tmp_path / "p.db")


def _ready_app(job_id: str, *, with_outreach=True) -> Application:
    app = Application(id=_app_id(job_id), job_id=job_id)
    advance(app, "ready", "prepared")
    if with_outreach:
        app.outreach = Outreach(
            contact_email="careers@acme.com", subject="Hi", body="Hello there"
        )
    return app


# --- auto-outreach gating ----------------------------------------------------
def test_auto_outreach_idempotent_when_already_sent(tmp_path):
    store, stats = _store(tmp_path), RunStats()
    job = JobPost(id="j1", source="t", title="ML Intern", company="Acme", url="")
    store.upsert_job(job)
    app = _ready_app("j1")
    app.outreach.sent_at = datetime.now()  # already emailed
    store.save_application(app)

    _auto_outreach(job, app, store, stats, _Settings(), log=lambda m: None)
    assert stats.emailed == 0  # never re-sends


def test_auto_outreach_skips_without_draft(tmp_path):
    store, stats = _store(tmp_path), RunStats()
    job = JobPost(id="j1", source="t", title="X", url="")
    store.upsert_job(job)
    app = _ready_app("j1", with_outreach=False)
    store.save_application(app)

    _auto_outreach(job, app, store, stats, _Settings(), log=lambda m: None)
    assert stats.emailed == 0


def test_auto_outreach_blocked_counts(tmp_path, monkeypatch):
    """A blocked send (e.g. suppression/cap) increments email_blocked, not emailed."""
    import piperline.orchestrator.pipeline as P
    from piperline.outreach.sender import SendResult

    store, stats = _store(tmp_path), RunStats()
    job = JobPost(id="j1", source="t", title="X", company="Acme", url="")
    store.upsert_job(job)
    app = _ready_app("j1")
    store.save_application(app)

    monkeypatch.setattr(
        "piperline.outreach.sender.send_email",
        lambda *a, **k: SendResult("careers@acme.com", "Hi", sent=False,
                                   blocked_reason="daily cap (20)"),
    )
    _auto_outreach(job, app, store, stats, _Settings(), log=lambda m: None)
    assert stats.email_blocked == 1 and stats.emailed == 0


def test_auto_apply_escalation_leaves_ready(tmp_path, monkeypatch):
    """A CAPTCHA/unmapped escalation must NOT mark applied — stays 'ready'."""
    from piperline.automator.apply import ApplyResult

    store, stats = _store(tmp_path), RunStats()
    job = JobPost(id="j1", source="t", title="X", company="Acme",
                  url="https://boards.greenhouse.io/acme/jobs/1")
    store.upsert_job(job)
    app = _ready_app("j1")
    store.save_application(app)

    monkeypatch.setattr(
        "piperline.automator.fill_application",
        lambda *a, **k: ApplyResult(url=job.url, ats="greenhouse",
                                    escalations=["CAPTCHA / bot-challenge present"],
                                    status="escalated"),
    )
    _auto_apply(job, app, None, store, stats, _Settings(), log=lambda m: None)
    assert stats.applied == 0 and stats.apply_escalated == 1
    assert store.get_application("j1").status == "ready"
    del store
    gc.collect()


# --- dashboard funnel --------------------------------------------------------
def test_funnel_counts_high_water_mark(tmp_path):
    """History decides the furthest stage, even if status was bumped back."""
    store = _store(tmp_path)
    job = JobPost(id="j1", source="t", title="X", company="Acme", url="")
    store.upsert_job(job)
    app = Application(id="a1", job_id="j1")
    for st in ("discovered", "scored", "tailored", "ready", "applied"):
        app.history.append(Event(at=datetime.now(), status=st))
    app.status = "ready"  # bumped back after, but it DID reach applied
    store.save_application(app)

    f = build_funnel(store)
    assert f.reached["applied"] == 1
    assert f.reached["discovered"] == 1  # cumulative
    assert f.conversion("ready", "applied") == 1.0
    del store
    gc.collect()


def test_funnel_side_branches_separate(tmp_path):
    store = _store(tmp_path)
    job = JobPost(id="j1", source="t", title="X", url="")
    store.upsert_job(job)
    app = Application(id="a1", job_id="j1")
    app.history.append(Event(at=datetime.now(), status="scored"))
    advance(app, "skipped", "below threshold")
    store.save_application(app)

    f = build_funnel(store)
    assert f.side["skipped"] == 1
    assert recent_activity(store)[0].status == "skipped"
    del store
    gc.collect()
