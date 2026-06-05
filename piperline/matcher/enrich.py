"""Synthesize raw signals (GitHub, later LinkedIn) into Profile-shaped data.

This is where "learn about me" becomes structured. An LLM reads the repo signals
and proposes Project and Skill entries. It must stay truthful — it summarizes
what's actually in the repos/READMEs, never inventing impact or metrics.

Output is *suggested* profile fragments the user reviews and merges, so the
Master Profile stays human-curated (VISION.md: one source of truth).
"""
from __future__ import annotations

import json

from piperline.config import Settings
from piperline.matcher.github import RepoSignal, language_histogram

_SYNTH_SYSTEM = """\
You are building a developer's professional profile from their GitHub repos.
Summarize ONLY what the repository metadata and README actually show. Never
invent metrics, users, dates, or outcomes that aren't stated. If impact is
unknown, describe what the project *does*, not fabricated results.
Return STRICT JSON matching the requested schema. No prose outside the JSON."""

_SYNTH_INSTRUCTIONS = """\
From the repositories below, produce JSON:
{
  "projects": [
    {"title": str, "summary": str, "impact": [str],
     "tech": [str], "links": {"repo": str, "demo": str?}}
  ],
  "skills": [{"name": str, "category": str, "level": str}],
  "headline": str,        // one line capturing what this person builds
  "interests": [str]      // themes you see across their work
}

Rules:
- Pick the most substantial/representative projects (skip trivial or empty ones).
- "impact" = concrete, truthful bullets from the README; [] if none stated.
- "tech" from languages, topics, and README.
- "level": infer "proficient"/"familiar" conservatively from usage frequency.
- Group skills sensibly (language/framework/tool/domain).

Repositories (JSON):
"""


def _repo_to_compact(s: RepoSignal) -> dict:
    return {
        "name": s.name,
        "description": s.description,
        "url": s.url,
        "homepage": s.homepage,
        "primary_language": s.primary_language,
        "languages": s.languages,
        "topics": s.topics,
        "stars": s.stars,
        "archived": s.is_archived,
        "readme_excerpt": (s.readme[:2500] if s.readme else None),
    }


def synthesize_from_github(
    signals: list[RepoSignal],
    *,
    settings: Settings,
) -> dict:
    """Ask the LLM to turn repo signals into suggested profile fragments."""
    from piperline import llm

    compact = [_repo_to_compact(s) for s in signals if not s.is_fork]
    payload = json.dumps(compact, ensure_ascii=False, indent=2)
    messages = [
        {"role": "system", "content": _SYNTH_SYSTEM},
        {"role": "user", "content": _SYNTH_INSTRUCTIONS + payload},
    ]
    result = llm.complete_json(messages, settings=settings)

    # Attach a deterministic language histogram as a cross-check / extra signal.
    result["_language_histogram"] = language_histogram(signals)
    return result
