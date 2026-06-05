"""Naukri browser-based scraper — bypasses API CAPTCHA issues.

Naukri's API returns 406 (reCAPTCHA required) for automated requests.
Using Playwright with stealth browser avoids this by looking like a real user.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piperline.common import JobPost

from piperline.common import JobPost


async def scrape_naukri_browser(
    search_term: str,
    location: str | None = None,
    results_wanted: int = 20,
    is_remote: bool = False,
    job_type: str | None = None,
) -> list[JobPost]:
    """Scrape Naukri using Playwright stealth browser to avoid CAPTCHA.

    Returns JobPost objects matching the search criteria.
    """
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    jobs = []

    # Build search URL
    search_query = search_term.replace(" ", "-")
    url = f"https://www.naukri.com/{search_query}-jobs"
    if location:
        url += f"-in-{location.lower().replace(' ', '-')}"

    try:
        async with async_playwright() as pw:
            # Use stealth browser
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                ],
            )

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                locale="en-IN",
            )

            # Apply stealth patches
            stealth = Stealth()
            stealth.use_sync(context)

            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for job listings to load
            await page.wait_for_selector('article.jobTuple, div.jobTuple', timeout=15000)

            # Extract job cards
            cards = await page.locator('article.jobTuple, div.jobTuple').all()

            for i, card in enumerate(cards[:results_wanted]):
                try:
                    # Title and link
                    title_el = card.locator('a.title, a[class*="title"]').first
                    if await title_el.count() == 0:
                        continue

                    title = await title_el.inner_text()
                    href = await title_el.get_attribute("href")

                    if not href:
                        continue
                    if not href.startswith("http"):
                        href = f"https://www.naukri.com{href}"

                    # Company
                    company_el = card.locator('a.subTitle, [class*="companyInfo"]').first
                    company = await company_el.inner_text() if await company_el.count() > 0 else None

                    # Location
                    loc_el = card.locator('[class*="location"]').first
                    job_location = await loc_el.inner_text() if await loc_el.count() > 0 else location

                    # Description snippet
                    desc_el = card.locator('[class*="jobDescription"], [class*="job-description"]').first
                    description = await desc_el.inner_text() if await desc_el.count() > 0 else ""

                    if title and href:
                        job = JobPost(
                            id=JobPost.make_id("naukri", None, href),
                            source="naukri",
                            title=title.strip()[:200],
                            company=company.strip() if company else None,
                            url=href,
                            description=description.strip()[:500],
                            location=job_location.strip() if job_location else None,
                            is_remote=is_remote,
                            job_type=job_type or "internship",
                        )
                        jobs.append(job)
                except Exception as e:
                    continue

            await browser.close()
    except Exception as e:
        print(f"Naukri browser scraping error: {e}")

    return jobs


def scrape_naukri_browser_sync(
    search_term: str,
    location: str | None = None,
    results_wanted: int = 20,
    is_remote: bool = False,
    job_type: str | None = None,
) -> list[JobPost]:
    """Synchronous wrapper for scrape_naukri_browser."""
    return asyncio.run(
        scrape_naukri_browser(search_term, location, results_wanted, is_remote, job_type)
    )
