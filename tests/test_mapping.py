"""Tests for the JobSpy -> JobPost mapping (the part most likely to drift)."""
import math

from piperline.aggregator.mapping import row_to_jobpost
from piperline.common import JobPost


def test_basic_mapping_and_emails():
    row = {
        "site": "indeed",
        "id": "xyz",
        "job_url": "http://example.com/job",
        "title": "Backend Intern",
        "company": "Acme",
        "location": "Remote",
        "is_remote": True,
        "job_type": "internship",
        "description": "Do backend things",
        "emails": "hr@acme.com, jobs@acme.com",
        "date_posted": "2026-05-20",
    }
    jp = row_to_jobpost(row)
    assert jp.source == "indeed"
    assert jp.title == "Backend Intern"
    assert jp.emails == ["hr@acme.com", "jobs@acme.com"]
    assert jp.is_remote is True
    assert jp.date_posted is not None and jp.date_posted.year == 2026


def test_nan_becomes_none():
    row = {
        "site": "linkedin",
        "job_url": "http://x",
        "title": "SWE",
        "company": float("nan"),
        "min_amount": float("nan"),
        "description": float("nan"),
    }
    jp = row_to_jobpost(row)
    assert jp.company is None
    assert jp.salary is None
    assert jp.description == ""  # NaN description coerced to empty string


def test_direct_url_preferred_and_salary():
    row = {
        "site": "glassdoor",
        "job_url": "http://posting",
        "job_url_direct": "http://apply-here",
        "title": "ML Intern",
        "min_amount": 1000.0,
        "max_amount": 2000.0,
        "interval": "monthly",
        "currency": "USD",
    }
    jp = row_to_jobpost(row)
    assert jp.url == "http://apply-here"
    assert jp.salary is not None
    assert jp.salary.min_amount == 1000.0
    assert jp.salary.interval == "monthly"


def test_make_id_is_stable_and_dedups():
    a = JobPost.make_id("linkedin", "123", "http://u")
    b = JobPost.make_id("linkedin", "123", "http://different")
    assert a == b  # same source+external_id -> same id regardless of url
    c = JobPost.make_id("indeed", "123", "http://u")
    assert a != c  # different source -> different id


def test_emails_empty_when_missing():
    jp = row_to_jobpost({"site": "google", "job_url": "http://x", "title": "T"})
    assert jp.emails == []
    assert jp.raw == {}
