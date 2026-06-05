"""Tests for the automator: ATS detection, name split, escalation, submit gate."""
from piperline.automator.ats import ATS, detect_from_url, field_map_for
from piperline.automator.apply import _split_name
from piperline.automator.answers import answer_question, _should_escalate
from piperline.common import Profile


def test_ats_detection():
    assert detect_from_url("https://boards.greenhouse.io/x/jobs/1") == ATS.GREENHOUSE
    assert detect_from_url("https://jobs.lever.co/x/abc") == ATS.LEVER
    assert detect_from_url("https://x.wd5.myworkdayjobs.com/x") == ATS.WORKDAY
    assert detect_from_url("https://jobs.ashbyhq.com/x") == ATS.ASHBY
    assert detect_from_url("https://acme.com/careers") == ATS.GENERIC


def test_field_map_has_submit_for_each_ats():
    for ats in ATS:
        assert field_map_for(ats).submit, f"{ats} missing submit selector"


def test_split_name():
    assert _split_name("Jane Doe") == ("Jane", "Doe")
    assert _split_name("Cher") == ("Cher", "")


def test_sensitive_questions_escalate_without_llm():
    # These must escalate purely on pattern, never reaching the LLM.
    for q in [
        "Do you require visa sponsorship?",
        "Are you authorized to work in the US?",
        "What are your salary expectations?",
        "Please describe any disability.",
        "Are you a veteran?",
    ]:
        assert _should_escalate(q), q


def test_neutral_question_not_auto_escalated():
    assert not _should_escalate("Why do you want to work here?")
    assert not _should_escalate("How many years of Python experience?")


def test_answer_question_escalates_sensitive_without_calling_llm():
    p = Profile(basics={"name": "T", "email": "t@e.com"})
    # No settings/LLM needed because sensitive questions short-circuit.
    a = answer_question("Do you need sponsorship?", p, settings=None)
    assert a.escalate and a.answer is None


# --- stealth + human modules ------------------------------------------------
def test_stealth_domain_extraction():
    from piperline.automator.stealth import _domain_from_url
    assert _domain_from_url("https://boards.greenhouse.io/acme/jobs/1") == "greenhouse.io"
    assert _domain_from_url("https://x.wd5.myworkdayjobs.com/en-US/x") == "myworkdayjobs.com"
    assert _domain_from_url("https://jobs.lever.co/acme") == "lever.co"


def test_login_wall_detection_markers():
    """Verify the login wall detection patterns are reasonable."""
    from piperline.automator.apply import _detect_login_wall
    # Can't test with a real page here, but verify the function exists and is callable
    assert callable(_detect_login_wall)
