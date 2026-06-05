"""Detect which Applicant Tracking System (ATS) a posting uses, and how to fill it.

Different ATSes (Greenhouse, Lever, Workday, Ashby) render predictable forms, so
detecting the platform lets us map our Profile to the right fields confidently.
Unknown sites fall back to a generic heuristic that matches fields by their label
text. Detection is URL-first (cheap) with an optional DOM check.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ATS(str, Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    ASHBY = "ashby"
    NAUKRI = "naukri"
    UNSTOP = "unstop"
    INTERNSHALA = "internshala"
    GENERIC = "generic"


# URL fingerprints -> ATS. Checked as substrings of the apply URL host/path.
_URL_SIGNATURES: list[tuple[str, ATS]] = [
    ("boards.greenhouse.io", ATS.GREENHOUSE),
    ("greenhouse.io", ATS.GREENHOUSE),
    ("jobs.lever.co", ATS.LEVER),
    ("lever.co", ATS.LEVER),
    ("myworkdayjobs.com", ATS.WORKDAY),
    ("workday", ATS.WORKDAY),
    ("jobs.ashbyhq.com", ATS.ASHBY),
    ("ashbyhq.com", ATS.ASHBY),
    ("naukri.com", ATS.NAUKRI),
    ("unstop.com", ATS.UNSTOP),
    ("internshala.com", ATS.INTERNSHALA),
]


def detect_from_url(url: str) -> ATS:
    u = (url or "").lower()
    for sig, ats in _URL_SIGNATURES:
        if sig in u:
            return ats
    return ATS.GENERIC


@dataclass
class FieldMap:
    """CSS selectors (or label keywords for generic) for standard fields."""
    first_name: list[str] = field(default_factory=list)
    last_name: list[str] = field(default_factory=list)
    full_name: list[str] = field(default_factory=list)
    email: list[str] = field(default_factory=list)
    phone: list[str] = field(default_factory=list)
    resume_upload: list[str] = field(default_factory=list)
    cover_letter_upload: list[str] = field(default_factory=list)
    linkedin: list[str] = field(default_factory=list)
    github: list[str] = field(default_factory=list)
    portfolio: list[str] = field(default_factory=list)
    submit: list[str] = field(default_factory=list)


# Per-ATS selector maps. Lists are tried in order; first match wins.
_MAPS: dict[ATS, FieldMap] = {
    ATS.GREENHOUSE: FieldMap(
        first_name=["#first_name", "input[name='first_name']"],
        last_name=["#last_name", "input[name='last_name']"],
        email=["#email", "input[name='email']"],
        phone=["#phone", "input[name='phone']"],
        resume_upload=["input[type='file'][name*='resume']", "input[type='file']"],
        cover_letter_upload=["input[type='file'][name*='cover']"],
        linkedin=["input[name*='linkedin' i]"],
        github=["input[name*='github' i]"],
        submit=["#submit_app", "button[type='submit']", "input[type='submit']"],
    ),
    ATS.LEVER: FieldMap(
        full_name=["input[name='name']"],
        email=["input[name='email']"],
        phone=["input[name='phone']"],
        resume_upload=["input[type='file'][name='resume']", "input[type='file']"],
        linkedin=["input[name*='urls[LinkedIn]' i]", "input[name*='linkedin' i]"],
        github=["input[name*='github' i]"],
        portfolio=["input[name*='portfolio' i]"],
        submit=["button[type='submit']", "button.template-btn-submit"],
    ),
    ATS.ASHBY: FieldMap(
        full_name=["input[name='_systemfield_name']", "input[aria-label*='name' i]"],
        email=["input[name='_systemfield_email']", "input[type='email']"],
        phone=["input[type='tel']"],
        resume_upload=["input[type='file']"],
        submit=["button[type='submit']"],
    ),
    ATS.WORKDAY: FieldMap(
        # Workday is heavily dynamic; these are best-effort and often need escalation.
        email=["input[data-automation-id='email']", "input[type='email']"],
        phone=["input[data-automation-id='phone-number']"],
        resume_upload=["input[type='file']"],
        submit=["button[data-automation-id='bottom-navigation-next-button']"],
    ),
    ATS.NAUKRI: FieldMap(
        # Naukri application forms (when not requiring login)
        full_name=["input[name='name']", "input[placeholder*='name' i]"],
        email=["input[name='email']", "input[type='email']"],
        phone=["input[name='mobile']", "input[name='phone']", "input[type='tel']"],
        resume_upload=["input[type='file'][name*='resume' i]", "input[type='file']"],
        submit=["button[type='submit']", "button:has-text('Apply')"],
    ),
    ATS.UNSTOP: FieldMap(
        # Unstop application forms
        full_name=["input[name='name']", "input[placeholder*='name' i]"],
        email=["input[name='email']", "input[type='email']"],
        phone=["input[name='phone']", "input[type='tel']"],
        resume_upload=["input[type='file']"],
        linkedin=["input[name*='linkedin' i]"],
        github=["input[name*='github' i]"],
        submit=["button[type='submit']", "button:has-text('Submit')"],
    ),
    ATS.INTERNSHALA: FieldMap(
        # Internshala application forms
        full_name=["input[name='name']", "input[id='name']"],
        email=["input[name='email']", "input[type='email']"],
        phone=["input[name='contact']", "input[name='phone']", "input[type='tel']"],
        resume_upload=["input[type='file'][name='resume']", "input[type='file']"],
        cover_letter_upload=["input[type='file'][name='cover_letter']"],
        submit=["button[type='submit']", "button:has-text('Apply')"],
    ),
    ATS.GENERIC: FieldMap(
        # For unknown sites we match by label keywords at fill time, but keep
        # type-based selectors as a backstop.
        email=["input[type='email']", "input[name*='email' i]", "input[id*='email' i]"],
        phone=["input[type='tel']", "input[name*='phone' i]"],
        full_name=["input[name*='name' i]", "input[id*='name' i]"],
        resume_upload=["input[type='file']"],
        submit=["button[type='submit']", "input[type='submit']", "button:has-text('Submit')"],
    ),
}


def field_map_for(ats: ATS) -> FieldMap:
    return _MAPS.get(ats, _MAPS[ATS.GENERIC])
