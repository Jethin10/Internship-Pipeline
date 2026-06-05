"""Pipeline state-machine tests — deterministic mode, no network, no LLM."""
import gc
from pathlib import Path

from piperline.common import Application, Education, Experience, JobPost, Profile, Project, Skill
from piperline.orchestrator.pipeline import RunStats, _app_id, _process_one
from piperline.store import Store, advance


class _Settings:
    """Minimal settings stand-in for the pipeline."""
    fit_threshold = 0.6
    deterministic_fit_threshold = 0.25


def _profile() -> Profile:
    return Profile(
        basics={"name": "T", "email": "t@e.com"},
        summary="ML and web builder",
        experience=[Experience(role="ML Intern", organization="Acme", tech=["Python"])],
        projects=[Project(title="Vision", tech=["YOLOv8", "Streamlit", "Python"])],
        skills=[Skill(name="Python"), Skill(name="Machine Learning"),
                Skill(name="Streamlit"), Skill(name="Computer Vision"), Skill(name="TypeScript")],
    )


def _store(tmp_path: Path) -> Store:
    return Store(tmp_path / "p.db")


def test_strong_job_passes_weak_job_skipped(tmp_path):
    store, profile, stats = _store(tmp_path), _profile(), RunStats()
    strong = JobPost(id="j1", source="t", title="Machine Learning Intern", company="V", url="",
                     description="python machine learning computer vision streamlit typescript")
    weak = JobPost(id="j2", source="t", title="Accountant", company="L", url="",
                   description="tax audit ledger excel sap quarterly filings")
    for j in (strong, weak):
        store.upsert_job(j)
        app = advance(Application(id=_app_id(j.id), job_id=j.id), "discovered")
        _process_one(j, app, profile, store, stats, _Settings(), use_llm=False, autopilot=False, log=lambda m: None)

    assert store.get_application("j1").status == "scored"   # passed prefilter, LLM off so stops here
    assert store.get_application("j2").status == "skipped"  # below deterministic threshold
    assert stats.scored == 2 and stats.skipped == 1
    del store
    gc.collect()


def test_idempotent_no_reprocess(tmp_path):
    """A job already advanced past 'discovered' is not reprocessed."""
    store, profile = _store(tmp_path), _profile()
    j = JobPost(id="j1", source="t", title="ML Intern", url="",
                description="python machine learning streamlit")
    store.upsert_job(j)
    app = advance(Application(id=_app_id(j.id), job_id=j.id), "ready")  # already done
    store.save_application(app)

    # second discovery pass: upsert returns False (dup), and we'd skip processing
    assert store.upsert_job(j) is False
    existing = store.get_application(j.id)
    assert existing.status == "ready"  # untouched
    del store
    gc.collect()
