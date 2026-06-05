"""Map JobSpy's scrape_jobs() DataFrame rows into our JobPost schema.

Isolated here so the rest of the system never imports jobspy or touches pandas.
Field names follow JobSpy's `desired_order` columns (see aggregator-jobspy).
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from piperline.common import JobPost, Salary


def _clean(value: Any) -> Any:
    """JobSpy uses NaN for missing cells; turn those into None."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _emails(value: Any) -> list[str]:
    value = _clean(value)
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(e).strip() for e in value if str(e).strip()]
    # JobSpy may hand back a comma-separated string
    return [e.strip() for e in str(value).split(",") if e.strip()]


def _salary(row: dict[str, Any]) -> Salary | None:
    mn = _clean(row.get("min_amount"))
    mx = _clean(row.get("max_amount"))
    interval = _clean(row.get("interval"))
    if mn is None and mx is None and interval is None:
        return None
    return Salary(
        interval=interval,
        min_amount=mn,
        max_amount=mx,
        currency=_clean(row.get("currency")),
    )


def _date(value: Any) -> date | None:
    value = _clean(value)
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# JobSpy columns we promote to first-class JobPost fields; the rest go in .raw
_PROMOTED = {
    "id", "site", "job_url", "job_url_direct", "title", "company", "location",
    "date_posted", "job_type", "is_remote", "emails", "description",
    "min_amount", "max_amount", "interval", "currency",
}


def row_to_jobpost(row: dict[str, Any]) -> JobPost:
    source = str(_clean(row.get("site")) or "unknown")
    url = str(_clean(row.get("job_url_direct")) or _clean(row.get("job_url")) or "")
    external_id = _clean(row.get("id"))

    raw = {k: v for k, v in row.items() if k not in _PROMOTED and _clean(v) is not None}

    return JobPost(
        id=JobPost.make_id(source, str(external_id) if external_id else None, url),
        source=source,
        title=str(_clean(row.get("title")) or "Untitled"),
        company=_clean(row.get("company")),
        location=_clean(row.get("location")),
        is_remote=_clean(row.get("is_remote")),
        job_type=_clean(row.get("job_type")),
        description=str(_clean(row.get("description")) or ""),
        url=url,
        emails=_emails(row.get("emails")),
        salary=_salary(row),
        date_posted=_date(row.get("date_posted")),
        raw=raw,
    )
