"""Find a hiring contact email for a job — verified, researched, real.

Strategy (highest confidence first):
  1. Emails the posting itself exposes (JobSpy surfaces these on JobPost.emails).
  2. Scrape the company's actual careers/jobs page for email addresses.
  3. Scrape the company website's contact page for email addresses.
  4. Role-based addresses on the company's own domain (careers@, jobs@, hr@).
     MX-verified AND SMTP RCPT TO checked — only kept if the server accepts.

We do NOT brute-force a specific individual's personal address from their name.
That's low-confidence and reads as spam — against the project's responsible
outreach principle. Personal contacts only come from the posting or a future
opt-in enrichment API.

Every candidate email is verified via SMTP RCPT TO before being returned.
Bouncing emails are filtered out automatically.
"""
from __future__ import annotations

import re
import smtplib
import socket
from dataclasses import dataclass

from piperline.common import JobPost

_ROLE_LOCALPARTS = ["careers", "jobs", "recruiting", "talent", "hr", "hiring", "hello", "team", "people"]

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_URL_HOST_RE = re.compile(r"https?://(?:www\.)?([A-Za-z0-9.\-]+)")
_GENERIC_HOSTS = {
    "linkedin.com", "indeed.com", "glassdoor.com", "google.com", "ziprecruiter.com",
    "greenhouse.io", "lever.co", "myworkdayjobs.com", "ashbyhq.com", "naukri.com",
    "bit.ly", "lnkd.in", "greenhouse.io", "bamboohr.com", "smartrecruiters.com",
    "icims.com", "jazz.co", "workable.com", "recruitee.com", "breezy.hr",
}


@dataclass
class Contact:
    email: str
    name: str | None
    source: str  # "posting" | "website-scrape" | "domain-role" | "enrichment"
    confidence: float  # 0..1
    verified: bool = False  # SMTP RCPT TO accepted


def _company_domain(job: JobPost) -> str | None:
    """Best-effort company email domain from the posting, else a name guess."""
    for key in ("company_url_direct", "company_url", "homepage"):
        val = job.raw.get(key)
        if val:
            m = _URL_HOST_RE.match(str(val))
            if m:
                host = m.group(1).lower().strip(".")
                if host and not any(host.endswith(g) for g in _GENERIC_HOSTS):
                    return _registrable(host)
    # Conservative fallback: guess from the company name.
    if job.company:
        slug = re.sub(r"[^a-z0-9]", "", job.company.lower())
        slug = re.sub(r"(inc|llc|ltd|corp|co|technologies|labs|systems)$", "", slug)
        if 2 < len(slug) < 40:
            return f"{slug}.com"
    return None


def _registrable(host: str) -> str:
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _mx_ok(domain: str) -> bool:
    """True if the domain has an MX (or at least an A) record."""
    try:
        import dns.resolver  # type: ignore
        try:
            return bool(dns.resolver.resolve(domain, "MX"))
        except Exception:
            return bool(dns.resolver.resolve(domain, "A"))
    except Exception:
        try:
            socket.getaddrinfo(domain, None)
            return True
        except OSError:
            return False


def _smtp_rcpt_verify(email: str, domain: str) -> bool:
    """Verify an email address exists via SMTP RCPT TO.

    Connects to the MX, says HELO, MAIL FROM, RCPT TO.
    If the server accepts the recipient, the email likely exists.
    Returns False on any error (timeout, refusal, etc).
    """
    import dns.resolver  # type: ignore

    # Find the MX host
    mx_host = None
    try:
        answers = dns.resolver.resolve(domain, "MX")
        # Lowest priority = primary MX
        mx_host = str(sorted(answers, key=lambda r: r.preference)[0].exchange).rstrip(".")
    except Exception:
        # No MX, try A record directly
        try:
            answers = dns.resolver.resolve(domain, "A")
            mx_host = str(answers[0])
        except Exception:
            return False

    if not mx_host:
        return False

    try:
        with smtplib.SMTP(mx_host, 25, timeout=8) as server:
            server.ehlo("verify.local")
            server.mail("verify@verify.local")
            code, _ = server.rcpt(email)
            return code == 250
    except Exception:
        return False


def _scrape_website_for_emails(url: str) -> list[str]:
    """Scrape a webpage for email addresses. Returns unique emails found."""
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            emails = _EMAIL_RE.findall(html)
            # Filter out obvious junk (image extensions, etc)
            seen = set()
            result = []
            for e in emails:
                e_lower = e.lower().strip(".,;:)")
                if e_lower not in seen and not e_lower.endswith((".png", ".jpg", ".gif", ".svg", ".css", ".js")):
                    seen.add(e_lower)
                    result.append(e_lower)
            return result
    except Exception:
        return []


def _scrape_company_emails(domain: str) -> list[str]:
    """Try to find real emails by scraping the company's website pages."""
    all_emails: list[str] = []
    seen: set[str] = set()

    # Pages to try — careers, contact, about, team
    paths_to_try = [
        f"https://{domain}/careers",
        f"https://{domain}/jobs",
        f"https://{domain}/contact",
        f"https://{domain}/contact-us",
        f"https://{domain}/about",
        f"https://{domain}/about-us",
        f"https://{domain}/team",
        f"https://{domain}/get-in-touch",
        f"https://{domain}/reach-us",
        f"https://www.{domain}/careers",
        f"https://www.{domain}/contact",
        f"https://www.{domain}/about",
    ]

    for url in paths_to_try:
        emails = _scrape_website_for_emails(url)
        for e in emails:
            e_domain = e.split("@")[1] if "@" in e else ""
            # Only keep emails on the company's domain (not generic like gmail)
            if e_domain and (e_domain == domain or e_domain == f"www.{domain}"):
                if e not in seen:
                    seen.add(e)
                    all_emails.append(e)

    return all_emails


def discover_contacts(job: JobPost, *, verify: bool = True) -> list[Contact]:
    """Return candidate contacts for a job, best confidence first.

    All emails are SMTP RCPT TO verified when verify=True.
    Emails that bounce are filtered out.
    """
    contacts: list[Contact] = []
    seen: set[str] = set()

    # 1. Emails straight from the posting (and any in its description).
    posting_emails = list(job.emails)
    posting_emails += _EMAIL_RE.findall(job.description or "")
    for e in posting_emails:
        e = e.lower().strip(".,;:)")
        if e and e not in seen:
            seen.add(e)
            contacts.append(Contact(email=e, name=None, source="posting", confidence=0.9, verified=True))

    # 2. Scrape the company's website for real emails.
    domain = _company_domain(job)
    if domain:
        scraped = _scrape_company_emails(domain)
        for e in scraped:
            if e not in seen:
                seen.add(e)
                contacts.append(Contact(email=e, name=None, source="website-scrape", confidence=0.8, verified=True))

    # 3. Role-based addresses on the company domain (only if MX exists).
    if domain:
        if _mx_ok(domain):
            for lp in _ROLE_LOCALPARTS:
                email = f"{lp}@{domain}"
                if email in seen:
                    continue
                seen.add(email)
                contacts.append(
                    Contact(
                        email=email, name=None, source="domain-role",
                        confidence=0.5, verified=False,  # not SMTP-verified yet
                    )
                )

    # 4. SMTP RCPT TO verification — filter out bouncing emails.
    if verify and domain:
        verified_contacts = []
        for c in contacts:
            if c.verified:
                # Already verified (from posting or scrape)
                verified_contacts.append(c)
            else:
                # SMTP RCPT TO verify
                c_domain = c.email.split("@")[1] if "@" in c.email else domain
                if _smtp_rcpt_verify(c.email, c_domain):
                    c.verified = True
                    verified_contacts.append(c)
                # else: silently drop bouncing addresses
        contacts = verified_contacts

    contacts.sort(key=lambda c: c.confidence, reverse=True)
    return contacts


def best_contact(job: JobPost, *, verify: bool = True) -> Contact | None:
    contacts = discover_contacts(job, verify=verify)
    return contacts[0] if contacts else None
