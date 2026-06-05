"""Unstop (formerly Dare2Compete) scraper — browser-based for Indian internships.

Unstop is a major platform for internships/competitions in India. Since they don't
have a public API and use heavy JavaScript rendering, we scrape via Playwright.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from piperline.common import JobPost

from piperline.common import JobPost


async def scrape_unstop(
    search_term: str,
    location: str | None = None,
    results_wanted: int = 20,
    is_remote: bool = False,
) -> list[JobPost]:
    """Scrape Unstop for internships using Playwright (stealth browser).

    Returns JobPost objects matching the search criteria.
    """
    from playwright.async_api import async_playwright
    from piperline.automator.stealth import _domain_from_url, _storage_path

    jobs = []
    url = "https://unstop.com/internships"

    try:
        async with async_playwright() as pw:
            # Use stealth browser to avoid detection
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
            )

            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Search if term provided
            if search_term:
                search_box = page.locator('input[placeholder*="Search" i]').first
                if await search_box.count() > 0:
                    await search_box.fill(search_term)
                    await search_box.press("Enter")
                    await page.wait_for_load_state("networkidle", timeout=15000)

            # Wait for job cards to load
            await page.wait_for_selector('a.card_new, div[class*="card"]', timeout=10000)

            # Extract job cards - Unstop uses a.card_new for internship cards
            cards = await page.locator('a[href*="/internships/"], a[href*="/opportunity/"]').all()

            for i, card in enumerate(cards[:results_wanted]):
                try:
                    # Get the href first
                    href = await card.get_attribute("href")
                    if not href:
                        continue

                    if not href.startswith("http"):
                        href = f"https://unstop.com{href}"

                    # Title is often in the card text or a nested element
                    title_el = card.locator('h2, h3, h4, [class*="title"]').first
                    if await title_el.count() > 0:
                        title = await title_el.inner_text()
                    else:
                        # Fallback: use card text
                        title = await card.inner_text()
                        title = title.split('\n')[0]  # First line is usually the title

                    # Company might be in a separate element
                    company_el = card.locator('[class*="company"], [class*="organization"]').first
                    company = await company_el.inner_text() if await company_el.count() > 0 else None

                    if title and href:
                        job = JobPost(
                            id=JobPost.make_id("unstop", None, href),
                            source="unstop",
                            title=title.strip()[:200],  # Limit title length
                            company=company.strip() if company else None,
                            url=href,
                            description="",  # Would need to visit detail page
                            location=location,
                            is_remote=is_remote,
                            job_type="internship",
                        )
                        jobs.append(job)
                except Exception as e:
                    continue

            await browser.close()
    except Exception as e:
        print(f"Unstop scraping error: {e}")

    return jobs


def scrape_unstop_sync(
    search_term: str,
    location: str | None = None,
    results_wanted: int = 20,
    is_remote: bool = False,
) -> list[JobPost]:
    """Synchronous wrapper for scrape_unstop."""
    return asyncio.run(scrape_unstop(search_term, location, results_wanted, is_remote))
