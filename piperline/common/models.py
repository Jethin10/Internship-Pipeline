"""Shared data contracts — the spine of the system.

These pydantic models are the stable interface between the three parts. As long
as they don't change, the aggregator, matcher, and automator can each be
rewritten independently. See ARCHITECTURE.md §3.
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# JobPost — produced by the Aggregator, consumed by everyone
# ---------------------------------------------------------------------------
class Salary(BaseModel):
    interval: str | None = None  # yearly | monthly | hourly ...
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str | None = None


class JobPost(BaseModel):
    id: str  # stable dedup key, see make_id()
    source: str  # "linkedin" | "indeed" | "greenhouse" | ...
    title: str
    company: str | None = None
    location: str | None = None
    is_remote: bool | None = None
    job_type: str | None = None  # "internship" | "fulltime" | ...
    description: str = ""
    url: str  # apply / posting URL
    emails: list[str] = Field(default_factory=list)  # contacts found in posting
    salary: Salary | None = None
    date_posted: date | None = None
    raw: dict[str, Any] = Field(default_factory=dict)  # source-specific extras

    @staticmethod
    def make_id(source: str, external_id: str | None, url: str) -> str:
        """Stable hash so the same posting is never processed twice."""
        basis = f"{source}::{external_id or url}".lower().strip()
        return hashlib.sha1(basis.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Application — the unit of work; lives in the store, drives the pipeline
# ---------------------------------------------------------------------------
ApplicationStatus = Literal[
    "discovered",  # found by aggregator
    "scored",      # matched against profile
    "tailored",    # resume + cover letter generated
    "ready",       # docs rendered, outreach drafted — awaiting apply/send
    "applied",     # submitted to the ATS/form
    "emailed",     # outreach sent
    "replied",     # a human replied
    "skipped",     # below fit threshold or user-skipped
    "error",       # something failed; see history
]


class Event(BaseModel):
    """One entry in an application's audit trail — makes runs resumable."""
    at: datetime
    status: ApplicationStatus
    note: str = ""


class Outreach(BaseModel):
    contact_email: str | None = None
    contact_name: str | None = None
    contact_source: str | None = None  # "posting" | "domain-guess" | "enrichment"
    subject: str | None = None
    body: str | None = None
    sent_at: datetime | None = None
    reply_at: datetime | None = None


class Application(BaseModel):
    id: str
    job_id: str  # -> JobPost.id  (idempotency: at most one per job)
    status: ApplicationStatus = "discovered"
    fit_score: float | None = None
    fit_rationale: str | None = None
    resume_path: str | None = None
    cover_letter_path: str | None = None
    outreach: Outreach | None = None
    history: list[Event] = Field(default_factory=list)
