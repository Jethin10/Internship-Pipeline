"""Internshala scraper — major Indian internship platform.

Internshala is one of India's largest internship platforms. Browser-based
scraping with stealth to avoid detection.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piperline.common import JobPost

from piperline.common import JobPost


async def scrape_internshala(
    search_term: str,
    location: str | None = None,
    results_wanted: int = 20,
    is_remote: bool = False,
) -> list[JobPost]:
    """Scrape Internshala for internships using Playwright.

    Returns JobPost objects matching the search criteria.
    """
    from playwright.async_api import async_playwright
    from playwright_stealth import Stealth

    jobs = []

    # Build search URL
    base_url = "https://internshala.com/internships"
    search_params = []
    if search_term:
        search_params.append(f"keywords={search_term.replace(' ', '%20')}")
    if location and not is_remote:
        search_params.append(f"location={location.replace(' ', '%20')}")
    if is_remote:
        search_params.append("type=virtual")

    url = f"{base_url}?{'&'.join(search_params)}" if search_params else base_url

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            )

            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                locale="en-IN",
            )

            stealth = Stealth()
            stealth.use_sync(context)

            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for internship cards
            await page.wait_for_selector('div.individual_internship', timeout=15000)

            # Extract internship cards
            cards = await page.locator('div.individual_internship').all()

            for i, card in enumerate(cards[:results_wanted]):
                try:
                    # Get link first (most reliable)
                    link_el = card.locator('a[href*="/internship/detail/"]').first
                    if await link_el.count() == 0:
                        continue

                    href = await link_el.get_attribute("href")
                    if not href:
                        continue
                    if not href.startswith("http"):
                        href = f"https://internshala.com{href}"

                    # Title - often in h3 or the link text
                    title_el = card.locator('h3, h4.profile').first
                    if await title_el.count() > 0:
                        title = await title_el.inner_text()
                    else:
                        # Fallback to link text
                        title = await link_el.inner_text()

                    # Company - usually in a span or div with company class
                    company_el = card.locator('[class*="company_name"], p.company_name').first
                    company = await company_el.inner_text() if await company_el.count() > 0 else None

                    # Location
                    loc_el = card.locator('div.location, [class*="location_link"]').first
                    job_location = await loc_el.inner_text() if await loc_el.count() > 0 else location

                    if title and href:
                        # Clean up title (remove extra whitespace/newlines)
                        title = " ".join(title.split()).strip()

                        job = JobPost(
                            id=JobPost.make_id("internshala", None, href),
                            source="internshala",
                            title=title[:200],
                            company=company.strip() if company else None,
                            url=href,
                            description="",
                            location=job_location.strip() if job_location else None,
                            is_remote=is_remote or ("work from home" in (job_location or "").lower()),
                            job_type="internship",
                        )
                        jobs.append(job)
                except Exception as e:
                    continue

            await browser.close()
    except Exception as e:
        print(f"Internshala scraping error: {e}")

    return jobs


def scrape_internshala_sync(
    search_term: str,
    location: str | None = None,
    results_wanted: int = 20,
    is_remote: bool = False,
) -> list[JobPost]:
    """Synchronous wrapper for scrape_internshala."""
    return asyncio.run(scrape_internshala(search_term, location, results_wanted, is_remote))
