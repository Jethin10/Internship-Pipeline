"""Tests for contact discovery (pure logic; MX check stubbed where needed)."""
from piperline.common import JobPost
from piperline.outreach.discovery import _company_domain, discover_contacts


def test_posting_emails_rank_highest():
    job = JobPost(id="1", source="indeed", title="X", company="Acme", url="",
                  emails=["hr@acme.com"],
                  description="Send your resume to careers@acme.io please.")
    contacts = discover_contacts(job, verify=False)
    top_two = {c.email for c in contacts[:2]}
    assert top_two == {"hr@acme.com", "careers@acme.io"}
    assert all(c.confidence == 0.9 for c in contacts if c.source == "posting")


def test_role_addresses_generated_on_domain():
    job = JobPost(id="1", source="indeed", title="X", company="Acme", url="",
                  raw={"company_url": "https://careers.acme.com/openings"})
    emails = {c.email for c in discover_contacts(job, verify=False)}
    assert "careers@acme.com" in emails
    assert "jobs@acme.com" in emails


def test_generic_boards_not_used_as_domain():
    job = JobPost(id="1", source="linkedin", title="X", company="Acme Corp", url="",
                  raw={"company_url": "https://www.linkedin.com/company/acme"})
    # Should ignore linkedin.com and fall back to a name guess
    domain = _company_domain(job)
    assert domain == "acme.com"


def test_name_guess_strips_suffixes():
    job = JobPost(id="1", source="indeed", title="X", company="Foo Technologies", url="")
    assert _company_domain(job) == "foo.com"


def test_no_domain_no_company():
    job = JobPost(id="1", source="indeed", title="X", url="")
    assert _company_domain(job) is None
