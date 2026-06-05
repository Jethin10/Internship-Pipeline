"""Render a Profile (or a tailored variant) to HTML and PDF.

The HTML path uses Jinja2 and has no native dependencies. The PDF path uses
WeasyPrint (optional `render` extra); if it's missing we raise a clear, actionable
error rather than crashing the whole pipeline.
"""
from __future__ import annotations

from pathlib import Path

from piperline.common import Profile

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_resume_html(
    profile: Profile,
    *,
    template: str = "resume.html.j2",
    accent: str = "#2563eb",
) -> str:
    """Render the resume to an HTML string."""
    env = _env()
    tmpl = env.get_template(template)
    return tmpl.render(p=profile, accent=accent)


def _pdf_via_chromium(html: str, out_path: Path) -> bool:
    """Render HTML->PDF with headless Chromium (Playwright). Most reliable on
    Windows — no GTK/native libs needed. Returns True on success."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return False
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            page.pdf(
                path=str(out_path),
                format="A4",
                print_background=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            browser.close()
        return True
    except Exception:
        return False


def _pdf_via_weasyprint(html: str, out_path: Path) -> bool:
    """Fallback PDF engine. Returns True on success."""
    try:
        from weasyprint import HTML  # type: ignore

        HTML(string=html, base_url=str(out_path.parent)).write_pdf(str(out_path))
        return True
    except Exception:
        return False


def render_resume_pdf(
    profile: Profile,
    out_path: Path,
    *,
    template: str = "resume.html.j2",
    accent: str = "#2563eb",
) -> Path:
    """Render the resume to a PDF at out_path.

    Tries headless Chromium first (reliable, cross-platform), then WeasyPrint.
    Always also writes the HTML alongside (.html) so there's a usable artifact
    even if no PDF engine is available.
    """
    html = render_resume_html(profile, template=template, accent=accent)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    html_path = out_path.with_suffix(".html")
    html_path.write_text(html, encoding="utf-8")

    if _pdf_via_chromium(html, out_path) or _pdf_via_weasyprint(html, out_path):
        return out_path

    raise RuntimeError(
        "No working PDF engine. Install a browser for Playwright with\n"
        "  .venv/Scripts/python.exe -m playwright install chromium\n"
        "or install the 'render' extra (WeasyPrint + GTK). The HTML resume was "
        f"still written to {html_path} — open it and 'Print to PDF' as a fallback."
    )
