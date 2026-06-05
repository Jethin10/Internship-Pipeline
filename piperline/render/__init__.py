"""Part B (start) — document rendering.

Turns a Profile (and later a tailored resume) into a styled HTML resume, then a
PDF if WeasyPrint is installed. HTML always works with zero native deps, so the
pipeline degrades gracefully when the optional `render` extra isn't present.
"""
from piperline.render.resume import render_resume_html, render_resume_pdf

__all__ = ["render_resume_html", "render_resume_pdf"]
