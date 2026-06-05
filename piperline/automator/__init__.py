"""Part B (apply) — browser automation to fill and submit applications.

Safety-first: fills + screenshots by default; submits only with autopilot ON and
explicit authorization. CAPTCHAs and anything ambiguous escalate to a human.
"""
from piperline.automator.apply import ApplyResult, fill_application
from piperline.automator.ats import ATS, detect_from_url

__all__ = ["fill_application", "ApplyResult", "ATS", "detect_from_url"]
