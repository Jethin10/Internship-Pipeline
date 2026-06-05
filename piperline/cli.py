"""Typer CLI — the human entrypoint to the pipeline.

v1 commands:
  piperline discover "backend intern" --location "Remote" --internship --hours 72
  piperline profile-check

More commands (run, apply, outreach) land with later milestones.
"""
from __future__ import annotations

import sys
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from piperline.aggregator import DiscoverQuery, discover

# Windows consoles default to cp1252 and choke on non-ASCII (★, accented company
# names, etc.). Force UTF-8 so output never crashes on a stray character.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

app = typer.Typer(
    add_completion=False,
    help="Intern Piperline — discover, tailor, apply, reach out.",
)
console = Console()


@app.command()
def discover_jobs(
    search_term: str = typer.Argument(..., help="e.g. 'backend developer intern'"),
    location: str = typer.Option(None, "--location", "-l"),
    remote: bool = typer.Option(False, "--remote"),
    internship: bool = typer.Option(False, "--internship", help="job_type=internship"),
    hours: int = typer.Option(None, "--hours", help="only postings newer than N hours"),
    results: int = typer.Option(20, "--results", "-n"),
    sites: str = typer.Option(
        None, "--sites", help="comma-separated; default linkedin,indeed,glassdoor,google,zip_recruiter"
    ),
):
    """Search job boards and print normalized openings."""
    query = DiscoverQuery(
        search_term=search_term,
        location=location,
        is_remote=remote,
        job_type="internship" if internship else None,
        hours_old=hours,
        results_wanted=results,
        sites=[s.strip() for s in sites.split(",")] if sites else DiscoverQuery.__dataclass_fields__["sites"].default_factory(),
    )
    console.print(f"[bold]Searching[/] for '{search_term}'…")
    posts = discover(query)
    console.print(f"Found [bold green]{len(posts)}[/] openings.\n")

    table = Table(show_lines=False)
    table.add_column("Source", style="cyan")
    table.add_column("Title")
    table.add_column("Company", style="magenta")
    table.add_column("Location")
    table.add_column("Emails", style="yellow")
    for p in posts:
        table.add_row(
            p.source,
            (p.title[:50]),
            (p.company or "")[:28],
            (p.location or "")[:24],
            ", ".join(p.emails) if p.emails else "-",
        )
    console.print(table)


@app.command()
def profile_check():
    """Load and validate the Master Profile, print a summary."""
    from piperline.matcher import load_profile

    profile = load_profile()
    console.print(f"[bold green]Profile OK[/] — {profile.basics.name}")
    console.print(
        f"  {len(profile.experience)} experiences · {len(profile.projects)} projects · "
        f"{len(profile.skills)} skills · {len(profile.achievements)} achievements"
    )


@app.command()
def analyze_github(
    username: str = typer.Argument(..., help="GitHub username, e.g. Jethin10"),
    forks: bool = typer.Option(False, "--forks", help="include forked repos"),
    no_readmes: bool = typer.Option(False, "--no-readmes", help="skip README fetch (faster)"),
):
    """Inspect a user's GitHub repos (no LLM key needed). Saves raw signal."""
    import json as _json
    from dataclasses import asdict

    from piperline.config import DATA_DIR
    from piperline.matcher.github import collect, language_histogram

    console.print(f"[bold]Analyzing[/] github.com/{username} …")
    signals = collect(username, include_forks=forks, with_readmes=not no_readmes)
    console.print(f"Collected [bold green]{len(signals)}[/] repos.\n")

    table = Table(show_lines=False)
    table.add_column("Repo", style="cyan")
    table.add_column("Lang", style="magenta")
    table.add_column("Stars", justify="right")
    table.add_column("Description")
    for s in signals:
        table.add_row(
            s.name[:28],
            (s.primary_language or "-")[:12],
            str(s.stars),
            (s.description or "")[:54],
        )
    console.print(table)

    hist = language_histogram(signals)
    console.print(f"\n[bold]Languages:[/] " + ", ".join(f"{k}({v})" for k, v in hist.items()))

    out = DATA_DIR / "raw" / f"github_{username}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        _json.dumps([asdict(s) for s in signals], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"\nRaw signal saved to [dim]{out}[/]")


@app.command()
def enrich_profile(
    username: str = typer.Argument(..., help="GitHub username to learn from"),
):
    """Use the LLM to turn GitHub repos into suggested profile fragments.

    Writes data/profile/suggested_from_github.yaml for you to review and merge
    into profile.yaml (the Master Profile stays human-curated).
    """
    import yaml

    from piperline.config import PROFILE_DIR, get_settings
    from piperline.matcher.enrich import synthesize_from_github
    from piperline.matcher.github import collect

    settings = get_settings()
    console.print(f"[bold]Learning[/] from github.com/{username} …")
    signals = collect(username, with_readmes=True)
    console.print(f"  read {len(signals)} repos; synthesizing with {settings.llm_model} …")

    suggested = synthesize_from_github(signals, settings=settings)
    out = PROFILE_DIR / "suggested_from_github.yaml"
    out.write_text(yaml.safe_dump(suggested, sort_keys=False, allow_unicode=True), encoding="utf-8")

    n_proj = len(suggested.get("projects", []))
    n_skill = len(suggested.get("skills", []))
    console.print(
        f"[bold green]Done.[/] {n_proj} projects, {n_skill} skills suggested.\n"
        f"Review and merge: [dim]{out}[/]"
    )
    if suggested.get("headline"):
        console.print(f"\nSuggested headline: [italic]{suggested['headline']}[/]")


@app.command()
def render_resume(
    out: str = typer.Option("data/output/resume.pdf", "--out", "-o", help="output path"),
    html_only: bool = typer.Option(False, "--html-only", help="skip PDF, write HTML only"),
    accent: str = typer.Option("#2563eb", "--accent", help="accent color hex"),
):
    """Render the Master Profile to a resume (HTML always; PDF if WeasyPrint present)."""
    from pathlib import Path

    from piperline.matcher import load_profile
    from piperline.render import render_resume_html, render_resume_pdf

    profile = load_profile()
    out_path = Path(out)

    if html_only:
        html = render_resume_html(profile, accent=accent)
        out_path = out_path.with_suffix(".html")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(html, encoding="utf-8")
        console.print(f"[bold green]HTML resume written:[/] {out_path}")
        return

    try:
        pdf_path = render_resume_pdf(profile, out_path, accent=accent)
        console.print(f"[bold green]PDF resume written:[/] {pdf_path}")
    except RuntimeError as e:
        console.print(f"[yellow]PDF unavailable[/] — {e}")


@app.command()
def tailor(
    jd_file: str = typer.Argument(..., help="path to a text file containing the job description"),
    title: str = typer.Option("Role", "--title", help="job title"),
    company: str = typer.Option(None, "--company"),
    out: str = typer.Option("data/output/tailored", "--out", "-o", help="output dir/stem"),
    cover_letter: bool = typer.Option(True, "--cover-letter/--no-cover-letter"),
    no_llm: bool = typer.Option(False, "--no-llm", help="deterministic score only, no tailoring"),
):
    """Score a JD against your profile, tailor a resume to it, render a PDF."""
    from pathlib import Path

    from piperline.common import JobPost
    from piperline.config import get_settings
    from piperline.matcher import load_profile
    from piperline.matcher.scorer import score_job
    from piperline.render import render_resume_pdf

    settings = get_settings()
    profile = load_profile()
    jd_text = Path(jd_file).read_text(encoding="utf-8")
    job = JobPost(
        id="tailor-cli", source="manual", title=title, company=company,
        url="", description=jd_text,
    )

    fit = score_job(job, profile, settings=settings, use_llm=not no_llm)
    console.print(f"[bold]Fit score:[/] [green]{fit.score}[/]  {fit.rationale}")
    if fit.missing_keywords:
        console.print(f"[dim]JD keywords not in your profile: {', '.join(fit.missing_keywords[:8])}[/]")

    if no_llm:
        console.print("[yellow]--no-llm set: scored only, skipping tailoring.[/]")
        return

    from piperline.matcher.tailor import tailor_resume

    console.print(f"Tailoring resume with {settings.llm_model} …")
    result = tailor_resume(job, profile, settings=settings)

    # Show the fabrication guard verdict prominently — truthfulness is core.
    if result.guard.ok:
        console.print(f"[bold green]{result.guard.summary()}[/]")
    else:
        console.print(f"[bold red]{result.guard.summary()}[/]")

    stem = Path(out)
    pdf_path = stem.with_suffix(".pdf")
    try:
        render_resume_pdf(result.profile, pdf_path, accent="#2563eb")
        console.print(f"[bold green]Tailored resume:[/] {pdf_path}")
    except RuntimeError as e:
        console.print(f"[yellow]PDF unavailable[/] — {e}")

    if cover_letter:
        from piperline.matcher.letters import draft_cover_letter

        letter = draft_cover_letter(job, profile, settings=settings)
        cl_path = stem.with_name(stem.name + "_cover_letter").with_suffix(".txt")
        cl_path.parent.mkdir(parents=True, exist_ok=True)
        cl_path.write_text(letter, encoding="utf-8")
        console.print(f"[bold green]Cover letter:[/] {cl_path}")


@app.command()
def run(
    search_term: str = typer.Argument(..., help="e.g. 'machine learning intern'"),
    location: str = typer.Option(None, "--location", "-l"),
    remote: bool = typer.Option(False, "--remote"),
    internship: bool = typer.Option(False, "--internship"),
    hours: int = typer.Option(None, "--hours", help="only postings newer than N hours"),
    results: int = typer.Option(15, "--results", "-n"),
    no_llm: bool = typer.Option(False, "--no-llm", help="deterministic scoring only, skip tailoring"),
):
    """Run the full read-only pipeline: discover -> score -> tailor -> render.

    Produces a ranked queue of 'ready' applications with tailored resumes + cover
    letters. Submits nothing and sends no email (those are later, gated stages).
    """
    from piperline.aggregator import DiscoverQuery
    from piperline.orchestrator import run_pipeline

    query = DiscoverQuery(
        search_term=search_term,
        location=location,
        is_remote=remote,
        job_type="internship" if internship else None,
        hours_old=hours,
        results_wanted=results,
    )
    console.print(f"[bold]Running pipeline[/] for '{search_term}'…")
    stats = run_pipeline(query, use_llm=not no_llm, on_event=lambda m: console.print(f"  {m}"))
    console.print(f"\n[bold green]Done.[/] {stats.summary()}")
    console.print("Review the queue with [cyan]piperline status[/].")


@app.command()
def autopilot(
    search_term: str = typer.Argument(..., help="e.g. 'machine learning intern'"),
    location: str = typer.Option(None, "--location", "-l"),
    remote: bool = typer.Option(False, "--remote"),
    internship: bool = typer.Option(True, "--internship/--no-internship"),
    hours: int = typer.Option(72, "--hours", help="only postings newer than N hours"),
    results: int = typer.Option(25, "--results", "-n"),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="skip the confirmation prompt (for unattended/scheduled runs)",
    ),
):
    """Fully automated loop: discover -> score -> tailor -> render -> APPLY -> EMAIL.

    This is the hands-off mode. It runs the whole pipeline AND acts on the world:
    it submits applications and sends outreach emails for every match above the
    fit threshold — but ONLY for the stages you've enabled in .env:

      AUTOPILOT_APPLY=true     -> auto-submit application forms
      AUTOPILOT_OUTREACH=true  -> auto-send outreach emails (needs SMTP_* too)

    Safety still holds even in autopilot: CAPTCHAs/logins/unmapped fields escalate
    (left at 'ready' for you), outreach respects the daily cap + suppression list,
    and nothing fabricates resume facts. Stages with autopilot OFF stop at 'ready'.
    """
    from piperline.aggregator import DiscoverQuery
    from piperline.config import get_settings
    from piperline.orchestrator import run_pipeline

    settings = get_settings()

    apply_on = settings.autopilot_apply
    email_on = settings.autopilot_outreach
    if not apply_on and not email_on:
        console.print(
            "[bold yellow]Both autopilot switches are OFF.[/] This run will behave "
            "like [cyan]run[/] — it stops at 'ready' and acts on nothing.\n"
            "Enable in config/.env:  AUTOPILOT_APPLY=true  AUTOPILOT_OUTREACH=true"
        )

    # Show exactly what will happen before it happens.
    console.print("\n[bold]Autopilot plan:[/]")
    console.print(f"  search: [cyan]{search_term}[/]  location: {location or 'any'}  "
                  f"internship={internship} remote={remote} hours={hours}")
    console.print(f"  auto-APPLY (submit forms):   "
                  + ("[bold green]ON[/]" if apply_on else "[dim]off[/]"))
    console.print(f"  auto-EMAIL (send outreach):  "
                  + ("[bold green]ON[/]" if email_on else "[dim]off[/]"))
    if email_on:
        console.print(f"  outreach daily cap: {settings.max_outreach_per_day}  "
                      f"from: {settings.smtp_user or '[red]SMTP not configured[/]'}")

    if (apply_on or email_on) and not yes:
        if not typer.confirm("\nProceed with world-acting autopilot?"):
            console.print("[yellow]Aborted.[/]")
            raise typer.Exit(1)

    query = DiscoverQuery(
        search_term=search_term,
        location=location,
        is_remote=remote,
        job_type="internship" if internship else None,
        hours_old=hours,
        results_wanted=results,
    )
    console.print(f"\n[bold]Autopilot running[/] for '{search_term}'…")
    stats = run_pipeline(
        query, settings=settings, use_llm=True, autopilot=True,
        on_event=lambda m: console.print(f"  {m}"),
    )
    console.print(f"\n[bold green]Autopilot done.[/] {stats.summary()}")
    console.print("Funnel + outcomes: [cyan]piperline dashboard[/]")


@app.command()
def dashboard(
    activity: int = typer.Option(12, "--activity", "-a", help="rows of recent activity to show"),
):
    """M9 — full funnel view: discovered -> ... -> applied -> emailed -> replied.

    Shows how many applications reached each stage, the conversion rate between
    consecutive stages, side-branches (skipped/error), and the latest activity.
    """
    from piperline.config import get_settings
    from piperline.orchestrator.dashboard import (
        FUNNEL_ORDER,
        build_funnel,
        recent_activity,
    )
    from piperline.store import Store

    store = Store(get_settings().db_path)
    f = build_funnel(store)
    if f.total == 0:
        console.print("No applications yet. Run [cyan]piperline run \"...\"[/] or "
                      "[cyan]piperline autopilot \"...\"[/] first.")
        return

    console.print(f"[bold]Application funnel[/]  ([dim]{f.total} total[/])\n")

    # Funnel table with per-stage count, bar, and conversion from previous stage.
    table = Table(show_lines=False)
    table.add_column("Stage", style="cyan")
    table.add_column("Reached", justify="right", style="green")
    table.add_column("", style="blue")  # bar
    table.add_column("Conv.", justify="right", style="magenta")

    top = max(f.reached.values()) or 1
    prev = None
    for stage in FUNNEL_ORDER:
        n = f.reached[stage]
        bar = "█" * round(20 * n / top)
        conv = ""
        if prev is not None:
            r = f.conversion(prev, stage)
            conv = f"{r*100:.0f}%" if r is not None else "-"
        table.add_row(stage, str(n), bar, conv)
        prev = stage
    console.print(table)

    side = ", ".join(f"{k}={v}" for k, v in f.side.items() if v)
    if side:
        console.print(f"\n[dim]side-branches:[/] {side}")

    # Recent activity feed.
    acts = recent_activity(store, limit=activity)
    if acts:
        console.print("\n[bold]Recent activity[/]")
        at = Table(show_lines=False)
        at.add_column("When", style="dim")
        at.add_column("Stage", style="cyan")
        at.add_column("Job", style="magenta")
        at.add_column("Note")
        for a in acts:
            at.add_row(a.when, a.status, a.job, a.note)
        console.print(at)


@app.command()
def status(
    show: str = typer.Option(None, "--status", help="filter: ready|scored|skipped|applied|..."),
):
    """Show the application funnel and the current queue from the store."""
    from piperline.config import get_settings
    from piperline.store import Store

    store = Store(get_settings().db_path)
    counts = store.status_counts()
    if not counts:
        console.print("No applications yet. Run [cyan]piperline run \"...\"[/] first.")
        return

    console.print("[bold]Funnel:[/] " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    apps = store.list_applications(status=show)
    table = Table(show_lines=False)
    table.add_column("Score", justify="right", style="green")
    table.add_column("Status", style="cyan")
    table.add_column("Job", style="magenta")
    table.add_column("Resume")
    for a in apps[:40]:
        job = store.get_job(a.job_id)
        table.add_row(
            f"{a.fit_score:.2f}" if a.fit_score is not None else "-",
            a.status,
            (f"{job.title} @ {job.company}" if job else a.job_id)[:50],
            "yes" if a.resume_path else "-",
        )
    console.print(table)


@app.command()
def outreach(
    draft: bool = typer.Option(False, "--draft", help="also draft messages with the LLM (needs key)"),
    limit: int = typer.Option(20, "--limit", "-n"),
):
    """Review the outreach queue: hiring contact + draft message per application.

    Discovers contacts for scored/ready applications (no key needed). With --draft,
    also generates the personalized message. Nothing is sent — this is the
    approve-only review queue.
    """
    from piperline.config import get_settings
    from piperline.outreach import discover_contacts
    from piperline.store import Store

    settings = get_settings()
    store = Store(settings.db_path)
    apps = [a for a in store.list_applications() if a.status in ("ready", "scored", "tailored")]
    if not apps:
        console.print("No applications to reach out about yet. Run [cyan]piperline run \"...\"[/].")
        return

    shown = 0
    for a in apps:
        if shown >= limit:
            break
        job = store.get_job(a.job_id)
        if not job:
            continue
        contacts = discover_contacts(job)
        best = contacts[0] if contacts else None
        shown += 1

        console.print(f"\n[bold magenta]{job.title}[/] @ {job.company}  [green]fit {a.fit_score}[/]")
        if best:
            v = "✓verified" if best.verified else "unverified"
            console.print(f"  contact: [yellow]{best.email}[/] ({best.source}, conf {best.confidence}, {v})")
        else:
            console.print("  contact: [dim]none found[/]")

        # Existing draft from a prior LLM run?
        if a.outreach and a.outreach.body:
            console.print(f"  [cyan]subject:[/] {a.outreach.subject}")
            console.print(f"  [dim]{a.outreach.body[:240]}[/]")
        elif draft and best is not None:
            try:
                from piperline.matcher import load_profile
                from piperline.matcher.letters import draft_outreach

                d = draft_outreach(job, load_profile(), settings=settings, contact_name=best.name)
                console.print(f"  [cyan]subject:[/] {d.subject}")
                console.print(f"  [dim]{d.body[:240]}[/]")
            except Exception as e:
                console.print(f"  [yellow]draft unavailable[/] ({type(e).__name__} — set LLM_API_KEY)")

    console.print(f"\n[dim]Showed {shown} application(s). Sending is not yet enabled (review-only).[/]")


@app.command()
def apply(
    job_id: str = typer.Argument(..., help="JobPost id from `status` (or a raw apply URL)"),
    submit: bool = typer.Option(False, "--submit", help="attempt submission (still requires autopilot)"),
    show_browser: bool = typer.Option(False, "--show-browser", help="run headed for debugging"),
):
    """Fill an application form (and submit only if autopilot is enabled).

    By default this FILLS the form and screenshots it for your review — it does
    NOT submit. Submission needs both --submit AND AUTOPILOT_APPLY=true in .env,
    and is blocked if anything (CAPTCHA, unmapped field) needs a human.
    """
    from pathlib import Path

    from piperline.automator import fill_application
    from piperline.config import DATA_DIR, get_settings
    from piperline.matcher import load_profile
    from piperline.store import Store

    settings = get_settings()
    profile = load_profile()
    store = Store(settings.db_path)

    app_rec = store.get_application(job_id)
    job = store.get_job(job_id)
    url = job.url if job else job_id  # allow passing a raw URL
    if not url:
        console.print("[red]No apply URL for that job.[/]")
        return

    resume = app_rec.resume_path if app_rec else None
    cover = app_rec.cover_letter_path if app_rec else None
    out_dir = DATA_DIR / "output" / job_id

    if not settings.autopilot_apply and submit:
        console.print("[yellow]AUTOPILOT_APPLY is off — will fill + screenshot only, not submit.[/]")

    console.print(f"[bold]Filling application[/] at {url} …")
    res = fill_application(
        url, profile, settings=settings, resume_path=resume, cover_letter_path=cover,
        screenshot_dir=out_dir, submit=submit, headless=not show_browser,
    )
    console.print(f"  ATS: [cyan]{res.ats}[/]  status: [bold]{res.status}[/]")
    console.print(f"  filled: {res.filled or '-'}  uploaded: {res.uploaded or '-'}")
    if res.escalations:
        console.print(f"  [yellow]needs you:[/] {'; '.join(res.escalations)}")
    if res.screenshot_path:
        console.print(f"  [dim]screenshot: {res.screenshot_path}[/]")
    if res.submitted:
        console.print("  [bold green]SUBMITTED[/]")
        if app_rec:
            from piperline.store import advance
            advance(app_rec, "applied", "submitted via automator")
            store.save_application(app_rec)
    elif res.error:
        console.print(f"  [red]error:[/] {res.error}")


@app.command()
def send_outreach(
    job_id: str = typer.Argument(None, help="send to one job, or omit to send the queue"),
    send: bool = typer.Option(False, "--send", help="actually send (still requires autopilot)"),
    limit: int = typer.Option(10, "--limit", "-n"),
):
    """Send outreach emails (dry-run by default; real send needs autopilot + --send).

    By default this is a DRY-RUN: it shows what would be sent but sends nothing.
    Real sending needs BOTH --send AND AUTOPILOT_OUTREACH=true in .env, plus SMTP
    config (SMTP_HOST/USER/PASS). Rate-limited to max_outreach_per_day.
    """
    from piperline.config import get_settings
    from piperline.outreach.sender import send_email
    from piperline.store import Store, advance

    settings = get_settings()
    store = Store(settings.db_path)
    apps = [store.get_application(job_id)] if job_id else store.list_applications(status="ready")
    apps = [a for a in apps if a and a.outreach and a.outreach.contact_email][:limit]

    if not apps:
        console.print("No applications with outreach drafts. Run [cyan]piperline run \"...\"[/] first.")
        return

    if not settings.autopilot_outreach and send:
        console.print("[yellow]AUTOPILOT_OUTREACH is off — will dry-run only, not send.[/]")

    sent_count = 0
    for a in apps:
        job = store.get_job(a.job_id)
        o = a.outreach
        console.print(f"\n[magenta]{job.title if job else a.job_id}[/]")
        console.print(f"  to: [yellow]{o.contact_email}[/]")
        console.print(f"  subject: {o.subject}")

        res = send_email(o.contact_email, o.subject, o.body, settings=settings, send=send)
        if res.sent:
            console.print("  [bold green]SENT[/]")
            advance(a, "emailed", f"sent to {o.contact_email}")
            o.sent_at = datetime.now()
            store.save_application(a)
            sent_count += 1
        elif res.dry_run:
            console.print("  [dim]dry-run (use --send + AUTOPILOT_OUTREACH=true to send)[/]")
        elif res.blocked_reason:
            console.print(f"  [yellow]blocked:[/] {res.blocked_reason}")
        elif res.error:
            console.print(f"  [red]error:[/] {res.error}")

    console.print(f"\n[bold]Sent {sent_count}[/] of {len(apps)} queued.")


if __name__ == "__main__":
    app()
