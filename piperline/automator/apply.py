"""Auto-fill (and, only when explicitly authorized, submit) an application form.

Anti-detection strategy (same as commercial apply tools):
  1. Stealth browser (playwright-stealth) — hides automation fingerprints
  2. Persistent sessions — cookies saved per domain, CAPTCHAs solved once
  3. Human-like interaction — realistic typing/clicking/scrolling
  4. CAPTCHA fallback — if still detected, pause for manual solve (interactive)
     or skip (unattended autopilot mode)

Safety model (VISION.md §7):
  - It FILLS standard fields and uploads docs, then takes a screenshot.
  - It does NOT submit unless BOTH settings.autopilot_apply is true AND the
    caller passes submit=True. Default is fill-and-screenshot for human review.
  - CAPTCHAs that can't be avoided are ESCALATED (or paused for manual solve).
  - It uses the user's real data only; it never invents answers.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from piperline.automator.ats import ATS, FieldMap, detect_from_url, field_map_for
from piperline.common import Profile
from piperline.config import Settings


@dataclass
class ApplyResult:
    url: str
    ats: str
    filled: list[str] = field(default_factory=list)      # fields we set
    uploaded: list[str] = field(default_factory=list)    # files attached
    escalations: list[str] = field(default_factory=list) # things needing a human
    screenshot_path: str | None = None
    submitted: bool = False
    status: str = "prepared"  # prepared | submitted | escalated | error
    error: str | None = None


def _split_name(full: str) -> tuple[str, str]:
    parts = full.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _first_visible(page, selectors: list[str]):
    """Return the first selector that resolves to a visible element, else None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                return loc
        except Exception:
            continue
    return None


def _detect_captcha(page) -> bool:
    markers = [
        "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']",
        "[class*='captcha' i]", "#cf-challenge-running",
        "iframe[src*='challenges.cloudflare.com']",
    ]
    for m in markers:
        try:
            if page.locator(m).first.count() > 0:
                return True
        except Exception:
            continue
    return False


def _detect_login_wall(page) -> bool:
    """Check if the page is a login/signup form rather than an application."""
    login_markers = [
        "input[type='password']",
        "button:has-text('Sign In')", "button:has-text('Log In')",
        "a:has-text('Create Account')", "a:has-text('Sign Up')",
        "[data-automation-id='signInLink']",  # Workday
    ]
    for m in login_markers:
        try:
            if page.locator(m).first.count() > 0:
                return True
        except Exception:
            continue
    return False


def _handle_captcha_or_login(
    page, pw, url: str, context, browser, result: ApplyResult,
    *, headless: bool, interactive: bool,
):
    """Handle CAPTCHA/login wall: pause for manual solve or escalate.

    In interactive mode (not -y/autopilot): relaunch headed, wait for user.
    In unattended mode: escalate and skip.
    """
    from piperline.automator.stealth import relaunch_headed, save_session

    is_captcha = _detect_captcha(page)
    is_login = _detect_login_wall(page)

    if not is_captcha and not is_login:
        return page, context, browser, False  # no issue

    issue = "CAPTCHA" if is_captcha else "login wall"

    if not interactive:
        # Unattended mode: can't pause for human, just escalate
        result.escalations.append(f"{issue} detected (unattended mode — skipped)")
        return page, context, browser, True  # blocked

    if headless:
        # Relaunch in headed mode so user can see and interact
        browser.close()
        browser, context, page = relaunch_headed(pw, url, context)
        page.goto(url, wait_until="domcontentloaded", timeout=45000)

    # Prompt user to solve it
    print(f"\n  ⚠️  {issue} detected at {url}")
    print("  Solve it in the browser window, then press Enter to continue...")
    try:
        input("  [Press Enter when done] ")
    except (EOFError, KeyboardInterrupt):
        result.escalations.append(f"{issue} — user cancelled")
        return page, context, browser, True

    # Save the session so we don't hit this again
    save_session(context, url)
    return page, context, browser, False


def fill_application(
    url: str,
    profile: Profile,
    *,
    settings: Settings,
    resume_path: str | Path | None = None,
    cover_letter_path: str | Path | None = None,
    screenshot_dir: str | Path | None = None,
    submit: bool = False,
    headless: bool = True,
    interactive: bool = True,  # False in autopilot -y mode (no user to solve CAPTCHAs)
) -> ApplyResult:
    """Open the posting, fill what we safely can, screenshot, optionally submit.

    Uses stealth browser + human-like interaction to avoid bot detection.
    """
    ats = detect_from_url(url)
    result = ApplyResult(url=url, ats=ats.value)
    fmap = field_map_for(ats)

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        result.status = "error"
        result.error = f"Playwright not available: {e}"
        return result

    try:
        from piperline.automator.human import (
            human_scroll,
            random_delay,
            wait_for_page_ready,
        )
        from piperline.automator.stealth import launch_stealth_browser, save_session

        with sync_playwright() as pw:
            browser, context, page = launch_stealth_browser(
                pw, url, headless=headless
            )

            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            wait_for_page_ready(page)

            # Initial scroll to look human
            human_scroll(page, "down", 200)
            random_delay(0.5, 1.0)

            # Check for CAPTCHA or login wall
            page, context, browser, blocked = _handle_captcha_or_login(
                page, pw, url, context, browser, result,
                headless=headless, interactive=interactive,
            )
            if blocked:
                result.status = "escalated"
                browser.close()
                return result

            # Re-check after potential manual solve
            wait_for_page_ready(page)

            # Fill the form with human-like interaction
            _populate(page, fmap, profile, resume_path, cover_letter_path, result)

            # Screenshot for human review BEFORE any submission.
            if screenshot_dir:
                shot = Path(screenshot_dir) / "application_filled.png"
                shot.parent.mkdir(parents=True, exist_ok=True)
                try:
                    page.screenshot(path=str(shot), full_page=True)
                    result.screenshot_path = str(shot)
                except Exception:
                    pass

            # Submission gate: requires autopilot ON, explicit submit=True, and no
            # outstanding escalations.
            may_submit = (
                submit and settings.autopilot_apply and not result.escalations
            )
            if may_submit:
                random_delay(0.5, 1.5)  # pause before submit like a human would
                btn = _first_visible(page, fmap.submit)
                if btn is not None:
                    from piperline.automator.human import move_and_click
                    move_and_click(page, btn)
                    page.wait_for_timeout(3000)
                    result.submitted = True
                    result.status = "submitted"
                else:
                    result.escalations.append("submit button not found")
            if not result.submitted:
                result.status = "escalated" if result.escalations else "prepared"

            # Save session cookies for future runs (avoid re-auth/re-CAPTCHA)
            save_session(context, url)
            browser.close()
    except Exception as e:
        result.status = "error"
        result.error = f"{type(e).__name__}: {e}"
    return result


def _populate(page, fmap: FieldMap, profile, resume_path, cover_letter_path, result):
    from piperline.automator.human import fill_like_human, random_delay

    b = profile.basics
    first, last = _split_name(b.name)

    _fill_human(page, fmap.first_name, first, "first_name", result)
    _fill_human(page, fmap.last_name, last, "last_name", result)
    _fill_human(page, fmap.full_name, b.name, "full_name", result)
    _fill_human(page, fmap.email, b.email, "email", result)
    _fill_human(page, fmap.phone, b.phone, "phone", result)
    _fill_human(page, fmap.linkedin, profile.links.get("linkedin"), "linkedin", result)
    _fill_human(page, fmap.github, profile.links.get("github"), "github", result)
    _fill_human(page, fmap.portfolio, profile.links.get("portfolio"), "portfolio", result)

    # File uploads (these don't need human-like typing).
    random_delay(0.3, 0.8)
    if resume_path and Path(resume_path).exists():
        loc = _first_visible(page, fmap.resume_upload) or _first_visible(page, ["input[type='file']"])
        if loc is not None:
            try:
                loc.set_input_files(str(resume_path))
                result.uploaded.append("resume")
            except Exception:
                result.escalations.append("resume upload failed")
    if cover_letter_path and Path(cover_letter_path).exists() and fmap.cover_letter_upload:
        loc = _first_visible(page, fmap.cover_letter_upload)
        if loc is not None:
            try:
                loc.set_input_files(str(cover_letter_path))
                result.uploaded.append("cover_letter")
            except Exception:
                pass


def _fill_human(page, selectors, value, label, result: ApplyResult) -> None:
    """Fill a field with human-like typing, or skip if not found."""
    from piperline.automator.human import fill_like_human, random_delay

    if not value:
        return
    loc = _first_visible(page, selectors)
    if loc is None:
        return
    try:
        fill_like_human(page, loc, str(value))
        result.filled.append(label)
        random_delay(0.2, 0.6)
    except Exception:
        result.escalations.append(f"could not fill {label}")
