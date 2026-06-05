"""Stealth browser launcher — anti-detection + persistent sessions.

Uses playwright-stealth to patch browser fingerprints so sites don't detect
automation. Stores cookies/localStorage per domain so CAPTCHAs and logins
persist across runs (solve once, reuse forever).

This is the same approach commercial apply tools (Simplify, LazyApply) use:
look human → CAPTCHAs rarely appear. When they do → reuse trusted cookies.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import TYPE_CHECKING

from piperline.config import DATA_DIR

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright

# Persistent browser state lives here, one dir per domain.
PROFILES_DIR = DATA_DIR / "browser_profiles"

# Common desktop viewports to randomize (avoids fingerprinting by fixed size).
_VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
]

# Common user-agents (Chrome on Windows — matches what most real users have).
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]


def _domain_from_url(url: str) -> str:
    """Extract the registrable domain for cookie bucketing."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or "unknown"
    # Keep the last two parts (e.g. greenhouse.io, lever.co, myworkdayjobs.com)
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _storage_path(domain: str) -> Path:
    return PROFILES_DIR / domain / "storage_state.json"


def launch_stealth_browser(
    pw: "Playwright",
    url: str,
    *,
    headless: bool = True,
) -> tuple["Browser", "BrowserContext", "Page"]:
    """Launch a stealth Chromium browser with persistent cookies for the domain.

    Returns (browser, context, page) — caller is responsible for closing.
    """
    from playwright_stealth import Stealth

    domain = _domain_from_url(url)
    storage = _storage_path(domain)
    viewport = random.choice(_VIEWPORTS)
    user_agent = random.choice(_USER_AGENTS)

    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )

    # Load saved cookies/localStorage if we have them for this domain.
    ctx_kwargs = {
        "viewport": viewport,
        "user_agent": user_agent,
        "locale": "en-US",
        "timezone_id": "America/New_York",
        "color_scheme": "light",
    }
    if storage.exists():
        ctx_kwargs["storage_state"] = str(storage)

    context = browser.new_context(**ctx_kwargs)

    # Apply stealth patches at the context level (all pages inherit them).
    stealth = Stealth(navigator_user_agent_override=user_agent)
    stealth.use_sync(context)

    page = context.new_page()

    return browser, context, page


def save_session(context: "BrowserContext", url: str) -> None:
    """Persist cookies + localStorage for this domain (call after successful interaction)."""
    domain = _domain_from_url(url)
    storage = _storage_path(domain)
    storage.parent.mkdir(parents=True, exist_ok=True)
    state = context.storage_state()
    storage.write_text(json.dumps(state, indent=2), encoding="utf-8")


def relaunch_headed(
    pw: "Playwright",
    url: str,
    context: "BrowserContext",
) -> tuple["Browser", "BrowserContext", "Page"]:
    """Relaunch in headed mode for manual CAPTCHA solving, preserving cookies."""
    # Save current state, close headless, reopen headed.
    domain = _domain_from_url(url)
    storage = _storage_path(domain)
    storage.parent.mkdir(parents=True, exist_ok=True)
    state = context.storage_state()
    storage.write_text(json.dumps(state, indent=2), encoding="utf-8")

    return launch_stealth_browser(pw, url, headless=False)
