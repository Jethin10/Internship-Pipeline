"""Intern Piperline — autonomous job/internship application engine.

Three decoupled parts coordinated by an orchestrator:
  A. aggregator   — discover + normalize openings (built on JobSpy)
  B. automator    — tailor docs, submit forms, send outreach (built fresh)
  C. matcher      — Master Profile + match/rank/tailor (built fresh, MCP-exposed)

See VISION.md / ARCHITECTURE.md / ROADMAP.md at the repo root.
"""

__version__ = "0.1.0"
