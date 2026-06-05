"""MCP server exposing the matcher brain as tools for Claude.

Exposes:
  - get_profile: load the Master Profile
  - match_job: score a JD against the profile
  - tailor_resume: generate a JD-tailored resume (with fabrication guard)
  - draft_cover_letter: write a cover letter
  - draft_outreach: write a personalized outreach email

Run with: python -m piperline.matcher_mcp.server
"""
import json
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from piperline.common import JobPost
from piperline.config import get_settings
from piperline.matcher import load_profile
from piperline.matcher.letters import draft_cover_letter, draft_outreach
from piperline.matcher.scorer import score_job
from piperline.matcher.tailor import tailor_resume

app = Server("piperline-matcher")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_profile",
            description="Load the user's Master Profile (education, experience, projects, skills)",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="discover_jobs",
            description="Search job boards (LinkedIn, Indeed, Glassdoor, etc.) for openings. Returns JobPost list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_term": {"type": "string", "description": "e.g. 'machine learning intern'"},
                    "location": {"type": "string"},
                    "is_remote": {"type": "boolean"},
                    "job_type": {"type": "string", "description": "internship, fulltime, contract"},
                    "hours_old": {"type": "number", "description": "only postings newer than N hours"},
                    "results_wanted": {"type": "number", "default": 15},
                },
                "required": ["search_term"],
            },
        ),
        Tool(
            name="match_job",
            description="Score how well a job description fits the user's profile (0-1 fit score + rationale)",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "description": {"type": "string", "description": "Full job description text"},
                },
                "required": ["title", "description"],
            },
        ),
        Tool(
            name="tailor_resume",
            description="Generate a resume tailored to a specific job (with fabrication guard)",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        ),
        Tool(
            name="draft_cover_letter",
            description="Write a cover letter for a job",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        ),
        Tool(
            name="draft_outreach",
            description="Write a short personalized outreach email to a hiring contact",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "description": {"type": "string"},
                    "contact_name": {"type": "string"},
                },
                "required": ["title", "description"],
            },
        ),
        Tool(
            name="find_contacts",
            description="Discover hiring contact emails for a job (from posting + domain role addresses)",
            inputSchema={
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "job_url": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["company"],
            },
        ),
        Tool(
            name="run_pipeline",
            description="Run the full pipeline: discover -> score -> tailor -> render. Returns stats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "search_term": {"type": "string"},
                    "location": {"type": "string"},
                    "is_remote": {"type": "boolean"},
                    "job_type": {"type": "string"},
                    "hours_old": {"type": "number"},
                    "results_wanted": {"type": "number", "default": 15},
                    "use_llm": {"type": "boolean", "default": True},
                },
                "required": ["search_term"],
            },
        ),
        Tool(
            name="get_status",
            description="Get the application funnel (counts by status) and top applications",
            inputSchema={
                "type": "object",
                "properties": {
                    "status_filter": {"type": "string", "description": "ready, scored, applied, etc."},
                    "limit": {"type": "number", "default": 20},
                },
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    settings = get_settings()
    profile = load_profile()

    if name == "get_profile":
        return [TextContent(type="text", text=profile.model_dump_json(indent=2))]

    if name == "discover_jobs":
        from piperline.aggregator import DiscoverQuery, discover
        query = DiscoverQuery(
            search_term=arguments["search_term"],
            location=arguments.get("location"),
            is_remote=arguments.get("is_remote", False),
            job_type=arguments.get("job_type"),
            hours_old=arguments.get("hours_old"),
            results_wanted=arguments.get("results_wanted", 15),
        )
        posts = discover(query, settings=settings)
        return [TextContent(
            type="text",
            text=json.dumps([{
                "id": p.id, "title": p.title, "company": p.company,
                "location": p.location, "url": p.url, "emails": p.emails,
                "description": p.description[:500],
            } for p in posts], indent=2),
        )]

    if name == "find_contacts":
        from piperline.outreach import discover_contacts
        job = JobPost(
            id="mcp", source="mcp", title="", company=arguments.get("company", ""),
            url=arguments.get("job_url", ""), description=arguments.get("description", ""),
        )
        contacts = discover_contacts(job)
        return [TextContent(
            type="text",
            text=json.dumps([{
                "email": c.email, "source": c.source, "confidence": c.confidence,
                "verified": c.verified,
            } for c in contacts[:5]], indent=2),
        )]

    if name == "run_pipeline":
        from piperline.aggregator import DiscoverQuery
        from piperline.orchestrator import run_pipeline
        query = DiscoverQuery(
            search_term=arguments["search_term"],
            location=arguments.get("location"),
            is_remote=arguments.get("is_remote", False),
            job_type=arguments.get("job_type"),
            hours_old=arguments.get("hours_old"),
            results_wanted=arguments.get("results_wanted", 15),
        )
        stats = run_pipeline(query, settings=settings, use_llm=arguments.get("use_llm", True))
        return [TextContent(type="text", text=stats.summary())]

    if name == "get_status":
        from piperline.store import Store
        store = Store(settings.db_path)
        counts = store.status_counts()
        apps = store.list_applications(status=arguments.get("status_filter"))
        limit = arguments.get("limit", 20)
        result = {"funnel": counts, "applications": []}
        for a in apps[:limit]:
            job = store.get_job(a.job_id)
            result["applications"].append({
                "job_id": a.job_id,
                "title": job.title if job else None,
                "company": job.company if job else None,
                "status": a.status,
                "fit_score": a.fit_score,
                "resume_path": a.resume_path,
            })
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    # All other tools need a JobPost from the arguments.
    job = JobPost(
        id="mcp-tool",
        source="mcp",
        title=arguments.get("title", ""),
        company=arguments.get("company"),
        url="",
        description=arguments.get("description", ""),
    )

    if name == "match_job":
        fit = score_job(job, profile, settings=settings)
        return [TextContent(
            type="text",
            text=json.dumps({
                "score": fit.score,
                "rationale": fit.rationale,
                "matched_skills": fit.matched_skills,
                "missing_keywords": fit.missing_keywords[:8],
            }, indent=2),
        )]

    if name == "tailor_resume":
        result = tailor_resume(job, profile, settings=settings)
        guard_status = "PASS" if result.guard.ok else f"FLAGS: {result.guard.flags}"
        return [TextContent(
            type="text",
            text=(
                f"Fabrication guard: {guard_status}\n\n"
                f"Tailored resume (JSON):\n{result.profile.model_dump_json(indent=2)}"
            ),
        )]

    if name == "draft_cover_letter":
        letter = draft_cover_letter(job, profile, settings=settings)
        return [TextContent(type="text", text=letter)]

    if name == "draft_outreach":
        draft = draft_outreach(
            job, profile, settings=settings,
            contact_name=arguments.get("contact_name"),
        )
        return [TextContent(
            type="text",
            text=f"Subject: {draft.subject}\n\n{draft.body}",
        )]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
