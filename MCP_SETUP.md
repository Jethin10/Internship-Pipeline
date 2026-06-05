# MCP Server Setup — for Claude Desktop & other MCP clients

The MCP server exposes **9 tools** covering the entire pipeline, so any MCP
client (Claude Desktop, Claude Code, etc.) can drive discovery, matching,
tailoring, and outreach.

## Tools Available

1. **get_profile** — load your Master Profile
2. **discover_jobs** — search job boards (LinkedIn, Indeed, Glassdoor, etc.)
3. **match_job** — score a JD against your profile (0-1 fit + rationale)
4. **tailor_resume** — generate a JD-tailored resume (with fabrication guard)
5. **draft_cover_letter** — write a cover letter
6. **draft_outreach** — write a personalized outreach email
7. **find_contacts** — discover hiring contact emails (posting + MX-verified role addresses)
8. **run_pipeline** — run the full discover→score→tailor→render loop
9. **get_status** — view the application funnel and queue

## Setup for Claude Desktop

1. **Copy the example config** to `claude_desktop_config.json` and edit the paths:
   ```bash
   cp claude_desktop_config.json.example claude_desktop_config.json
   ```

2. **Edit the paths** in `claude_desktop_config.json` — replace `ABSOLUTE/PATH/TO/...`
   with the actual absolute paths on your machine.

3. **Copy to Claude Desktop's config location:**
   ```bash
   # Windows
   copy claude_desktop_config.json %APPDATA%\Claude\claude_desktop_config.json

   # macOS
   cp claude_desktop_config.json ~/Library/Application\ Support/Claude/claude_desktop_config.json

   # Linux
   cp claude_desktop_config.json ~/.config/Claude/claude_desktop_config.json
   ```

4. **Restart Claude Desktop** — it will auto-connect to the MCP server.

5. **Verify** — in a new chat, ask Claude to use the tools:
   ```
   "Use the internship-pipeline MCP to discover ML internships"
   "Get my profile and tailor a resume for this JD: [paste]"
   ```

## What You Can Do

With these tools, any MCP client can:

- **Discover jobs** on command: "Find 20 remote ML internships posted in the last 48 hours"
- **Score any JD** you paste: "How well do I fit this role?" → instant 0-1 score + matched skills
- **Tailor resumes** on the fly: "Tailor my resume for this JD" → fabrication-guarded output
- **Draft everything**: cover letters + outreach emails, all grounded in your real profile
- **Run the full pipeline**: "Run the pipeline for backend intern roles in NYC" → discover, score, tailor, render, queue
- **Check status**: "Show me the top 10 ready applications" → funnel + ranked list

## Testing the Server Standalone

```bash
# Verify it starts (Ctrl+C to exit)
.venv/Scripts/python.exe -m piperline.matcher_mcp.server    # Windows
# .venv/bin/python -m piperline.matcher_mcp.server            # macOS/Linux
```

It should wait for stdin (MCP protocol). If it imports cleanly, it's ready.

## Permissions

The MCP server runs with full access to:
- Your profile (`data/profile/profile.yaml`)
- The store (`data/piperline.db`)
- JobSpy (live job discovery)
- The LLM (via your `LLM_API_KEY` in `config/.env`)

It does **not** auto-submit applications or send emails — those still require
the gated CLI commands with autopilot switches. The MCP tools are read-heavy +
draft-generation, which is exactly what an AI assistant needs to help you
review and decide.
