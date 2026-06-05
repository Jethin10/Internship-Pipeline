"""Human-like browser interaction — realistic typing, clicking, scrolling.

reCAPTCHA v3 (invisible) scores behavior: instant fills + robotic clicks = bot.
Adding realistic variance to timing and movement makes the automation pass as
human interaction, which means the invisible CAPTCHA gives a high trust score
and never shows a challenge.

These utilities wrap Playwright actions with human-speed timing.
"""
from __future__ import annotations

import random
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page


def random_delay(min_s: float = 0.3, max_s: float = 1.2) -> None:
    """Sleep a random human-like duration between actions."""
    time.sleep(random.uniform(min_s, max_s))


def type_like_human(locator: "Locator", text: str, *, speed: str = "normal") -> None:
    """Type text character by character with realistic inter-key delays.

    speed: "fast" (50-100ms), "normal" (80-180ms), "slow" (120-250ms)
    """
    delays = {"fast": (50, 100), "slow": (120, 250), "normal": (80, 180)}
    lo, hi = delays.get(speed, delays["normal"])

    locator.click()
    random_delay(0.1, 0.3)

    for char in text:
        locator.press_sequentially(char, delay=random.randint(lo, hi))
        # Occasional micro-pause (like a human thinking mid-word)
        if random.random() < 0.05:
            time.sleep(random.uniform(0.3, 0.8))


def move_and_click(page: "Page", locator: "Locator") -> None:
    """Move mouse to element with a slight curve, then click with a small delay."""
    try:
        box = locator.bounding_box()
        if box:
            # Move to a slightly randomized point within the element
            x = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            y = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            page.mouse.move(x, y, steps=random.randint(5, 15))
            random_delay(0.05, 0.15)
            page.mouse.click(x, y)
        else:
            locator.click()
    except Exception:
        locator.click()


def human_scroll(page: "Page", direction: str = "down", amount: int = 300) -> None:
    """Scroll the page like a human — variable speed, not instant."""
    delta = amount if direction == "down" else -amount
    # Scroll in small increments
    steps = random.randint(3, 6)
    per_step = delta // steps
    for _ in range(steps):
        page.mouse.wheel(0, per_step + random.randint(-20, 20))
        time.sleep(random.uniform(0.05, 0.15))


def fill_like_human(
    page: "Page",
    locator: "Locator",
    value: str,
    *,
    clear_first: bool = True,
) -> None:
    """Click a field, optionally clear it, then type with human speed."""
    move_and_click(page, locator)
    random_delay(0.1, 0.4)

    if clear_first:
        # Select all + delete (like a human would)
        locator.press("Control+a")
        random_delay(0.05, 0.15)
        locator.press("Backspace")
        random_delay(0.1, 0.2)

    type_like_human(locator, value)
    random_delay(0.2, 0.5)


def wait_for_page_ready(page: "Page", timeout: int = 10000) -> None:
    """Wait for the page to be interactive (network idle + DOM stable)."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass  # Some pages never reach networkidle; that's fine
    random_delay(0.5, 1.5)
