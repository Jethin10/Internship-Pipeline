"""Login helper — opens a headed browser so you can log into job boards.

Run this ONCE to save your session cookies. After logging in, close the
browser window. The cookies are saved automatically and the autopilot
will reuse them for future applications.

Usage:
  .venv\Scripts\python.exe login_helper.py
"""
import json
import sys
import time
from pathlib import Path

# Force UTF-8 on Windows consoles
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

PROFILES_DIR = Path(__file__).parent / "data" / "browser_profiles"

SITES = [
    ("LinkedIn", "https://www.linkedin.com/login"),
    ("Indeed", "https://secure.indeed.com/auth"),
    ("Naukri", "https://www.naukri.com/nlogin/login"),
]


def save_storage(context, domain: str):
    storage_path = PROFILES_DIR / domain / "storage_state.json"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    state = context.storage_state()
    storage_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"  [SAVED] Cookies for {domain} -> {storage_path}")


def main():
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    print("=" * 55)
    print("  LOGIN HELPER — Intern Piperline")
    print("=" * 55)
    print()
    print("A browser window will open for each job board.")
    print("Log in normally, then CLOSE the browser window.")
    print("Cookies are saved automatically when you close.")
    print()

    with sync_playwright() as pw:
        for name, url in SITES:
            input(f"Press Enter to open {name} login page...")

            browser = pw.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                locale="en-US",
            )
            stealth = Stealth()
            stealth.use_sync(context)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")

            print(f"\n  >> {name} is open. Log in, then CLOSE the browser window.")
            print(f"     (Don't click any 'Stay signed in' popups if you don't want to)")

            # Wait for the browser to be closed by the user
            try:
                page.wait_for_event("close", timeout=600_000)  # 10 min max
            except Exception:
                pass

            # Save cookies after user closes
            domain = url.split("//")[-1].split("/")[0].replace("www.", "")
            try:
                save_storage(context, domain)
            except Exception as e:
                print(f"  [WARN] Could not save cookies for {domain}: {e}")

            try:
                browser.close()
            except Exception:
                pass

            print()

    print("=" * 55)
    print("  DONE! All sessions saved.")
    print("  Now run: piperline autopilot ...")
    print("=" * 55)


if __name__ == "__main__":
    main()
