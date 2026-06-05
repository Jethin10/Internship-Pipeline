"""discover(query) -> list[JobPost].

Fans out to JobSpy for the requested boards, normalizes rows, and dedups by the
stable JobPost.id. ToS-sensitive scraping is isolated here (rate limits, proxies,
backoff live with the source, not the rest of the system).

Unstop is handled separately via Playwright since it requires browser-based scraping.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from piperline.aggregator.mapping import row_to_jobpost
from piperline.common import JobPost
from piperline.config import Settings, get_settings

# Boards JobSpy supports out of the box.
# Note: Naukri has aggressive bot detection (API returns 406, browser gets "Access Denied")
# Use Unstop and Internshala for Indian internships instead.
# Glassdoor: consistently errors. ZipRecruiter: 403 forbidden. Excluded.
DEFAULT_SITES = ["linkedin", "indeed", "google", "unstop", "internshala"]


@dataclass
class DiscoverQuery:
    """A single search across one or more job boards."""
    search_term: str
    location: str | None = None
    sites: list[str] = field(default_factory=lambda: list(DEFAULT_SITES))
    is_remote: bool = False
    job_type: str | None = None  # "internship" | "fulltime" | "contract" | ...
    results_wanted: int = 20
    hours_old: int | None = None  # freshness filter, e.g. 72
    google_search_term: str | None = None  # required for good Google results
    linkedin_fetch_description: bool = True  # get full JD + direct URL


def discover(
    query: DiscoverQuery,
    *,
    settings: Settings | None = None,
) -> list[JobPost]:
    """Run the query against JobSpy and return deduped JobPosts.

    Unstop and Naukri are handled separately via Playwright browser scraping
    to avoid CAPTCHA issues.
    """
    s = settings or get_settings()
    posts: dict[str, JobPost] = {}

    # Separate browser-based scrapers from JobSpy sites
    jobspy_sites = [site for site in query.sites if site not in ("unstop", "naukri", "internshala")]
    has_unstop = "unstop" in query.sites
    has_naukri = "naukri" in query.sites
    has_internshala = "internshala" in query.sites

    # Run JobSpy for standard sites
    if jobspy_sites:
        from jobspy import scrape_jobs

        proxies = (
            [p.strip() for p in s.proxies.split(",") if p.strip()] if s.proxies else None
        )

        kwargs: dict = {
            "site_name": jobspy_sites,
            "search_term": query.search_term,
            "location": query.location,
            "is_remote": query.is_remote,
            "results_wanted": query.results_wanted,
            "country_indeed": s.default_country_indeed,
            "linkedin_fetch_description": query.linkedin_fetch_description,
            "description_format": "markdown",
            "verbose": 0,
        }
        if query.job_type:
            kwargs["job_type"] = query.job_type
        if query.hours_old is not None:
            kwargs["hours_old"] = query.hours_old
        if query.google_search_term:
            kwargs["google_search_term"] = query.google_search_term
        if proxies:
            kwargs["proxies"] = proxies

        df = scrape_jobs(**kwargs)

        if df is not None and not df.empty:
            from piperline.aggregator.mapping import row_to_jobpost
            for record in df.to_dict(orient="records"):
                post = row_to_jobpost(record)
                posts.setdefault(post.id, post)  # dedup by stable id

    # Run Naukri browser scraper if requested
    if has_naukri:
        try:
            from piperline.aggregator.naukri_browser import scrape_naukri_browser_sync
            naukri_jobs = scrape_naukri_browser_sync(
                search_term=query.search_term,
                location=query.location,
                results_wanted=query.results_wanted,
                is_remote=query.is_remote,
                job_type=query.job_type,
            )
            for job in naukri_jobs:
                posts.setdefault(job.id, job)
        except Exception as e:
            print(f"Naukri browser scraping failed: {e}")

    # Run Unstop scraper if requested
    if has_unstop:
        try:
            from piperline.aggregator.unstop import scrape_unstop_sync
            unstop_jobs = scrape_unstop_sync(
                search_term=query.search_term,
                location=query.location,
                results_wanted=query.results_wanted,
                is_remote=query.is_remote,
            )
            for job in unstop_jobs:
                posts.setdefault(job.id, job)
        except Exception as e:
            print(f"Unstop scraping failed: {e}")

    # Run Internshala scraper if requested
    if has_internshala:
        try:
            from piperline.aggregator.internshala import scrape_internshala_sync
            internshala_jobs = scrape_internshala_sync(
                search_term=query.search_term,
                location=query.location,
                results_wanted=query.results_wanted,
                is_remote=query.is_remote,
            )
            for job in internshala_jobs:
                posts.setdefault(job.id, job)
        except Exception as e:
            print(f"Internshala scraping failed: {e}")

    return list(posts.values())
