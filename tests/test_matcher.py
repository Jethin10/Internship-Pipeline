"""Tests for fit scoring and the fabrication guard (pure logic, no LLM)."""
import copy

from piperline.common import Experience, JobPost, Profile, Project, Skill
from piperline.matcher.scorer import deterministic_score
from piperline.matcher.tailor import fabrication_guard


def _profile() -> Profile:
    return Profile(
        basics={"name": "Test User", "email": "t@e.com"},
        summary="Builds ML and web things.",
        experience=[Experience(role="ML Intern", organization="Acme", highlights=["Trained models"], tech=["Python"])],
        projects=[Project(title="VisionApp", impact=["Detected objects"], tech=["YOLOv8", "Streamlit"])],
        achievements=["Won a hackathon"],
        skills=[Skill(name="Python"), Skill(name="Machine Learning"), Skill(name="Streamlit")],
    )


def test_strong_jd_scores_higher_than_weak():
    p = _profile()
    strong = JobPost(id="1", source="t", title="ML Intern", url="",
                     description="Python machine learning with Streamlit and model training")
    weak = JobPost(id="2", source="t", title="Accountant", url="",
                   description="Manage ledgers, tax filings, and quarterly audits")
    s_strong = deterministic_score(strong, p).score
    s_weak = deterministic_score(weak, p).score
    assert s_strong > s_weak
    assert s_weak == 0.0


def test_matched_skills_surface():
    p = _profile()
    job = JobPost(id="1", source="t", title="Dev", url="",
                  description="We use python and streamlit daily")
    r = deterministic_score(job, p)
    assert "Python" in r.matched_skills
    assert "Streamlit" in r.matched_skills


def test_guard_passes_for_subset():
    p = _profile()
    tailored = copy.deepcopy(p)
    tailored.skills = tailored.skills[:2]  # subset/reorder is fine
    assert fabrication_guard(tailored, p).ok


def test_guard_flags_fabricated_entries():
    p = _profile()
    bad = copy.deepcopy(p)
    bad.experience.append(Experience(role="CTO", organization="Microsoft", highlights=[]))
    bad.projects.append(Project(title="Quantum Computer"))
    bad.skills.append(Skill(name="Haskell"))
    report = fabrication_guard(bad, p)
    assert not report.ok
    joined = " ".join(report.flags)
    assert "Microsoft" in joined
    assert "Quantum Computer" in joined
    assert "Haskell" in joined
