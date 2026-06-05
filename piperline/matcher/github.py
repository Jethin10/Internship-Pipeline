"""Learn about the user from their GitHub — repos, languages, READMEs.

Part of the "Understand Me" core (VISION.md step 2). Fetches the user's public
repositories and their READMEs via the `gh` CLI (already authenticated) or a
GITHUB_TOKEN, then an LLM synthesizes them into Profile-shaped projects + skills.

We fetch raw signal here; synthesis into the Profile lives in `enrich.py`.
"""
from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class RepoSignal:
    """Everything we learned about one repository."""
    name: str
    description: str | None
    url: str
    homepage: str | None
    primary_language: str | None
    languages: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    stars: int = 0
    forks: int = 0
    is_fork: bool = False
    is_archived: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    readme: str | None = None  # truncated README text


def _gh(args: list[str]) -> str:
    """Run a gh CLI command and return stdout. Raises on failure."""
    result = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def fetch_repos(username: str, *, include_forks: bool = False) -> list[dict]:
    """List the user's repos with metadata via `gh repo list`."""
    out = _gh([
        "repo", "list", username,
        "--limit", "200",
        "--json",
        "name,description,primaryLanguage,languages,stargazerCount,forkCount,"
        "isFork,repositoryTopics,updatedAt,createdAt,url,homepageUrl,isArchived",
    ])
    repos = json.loads(out)
    if not include_forks:
        repos = [r for r in repos if not r.get("isFork")]
    return repos


def fetch_readme(username: str, repo: str, *, max_chars: int = 6000) -> str | None:
    """Fetch a repo's README via the API, decoded and truncated. None if absent."""
    try:
        out = _gh(["api", f"repos/{username}/{repo}/readme", "--jq", ".content"])
    except RuntimeError:
        return None  # no README
    import base64

    try:
        text = base64.b64decode(out.strip()).decode("utf-8", errors="replace")
    except Exception:
        return None
    text = text.strip()
    return text[:max_chars] if text else None


def _topics(repo: dict) -> list[str]:
    topics = repo.get("repositoryTopics") or []
    # gh returns either [{"name": "x"}] or ["x"] depending on version
    out = []
    for t in topics:
        out.append(t["name"] if isinstance(t, dict) else str(t))
    return out


def collect(
    username: str,
    *,
    include_forks: bool = False,
    with_readmes: bool = True,
    max_repos: int | None = None,
) -> list[RepoSignal]:
    """Gather RepoSignals for a user, newest first, READMEs included by default."""
    repos = fetch_repos(username, include_forks=include_forks)
    repos.sort(key=lambda r: r.get("updatedAt") or "", reverse=True)
    if max_repos:
        repos = repos[:max_repos]

    signals: list[RepoSignal] = []
    for r in repos:
        lang_obj = r.get("primaryLanguage") or {}
        languages = [
            (l["node"]["name"] if isinstance(l, dict) and "node" in l else
             l.get("name") if isinstance(l, dict) else str(l))
            for l in (r.get("languages") or [])
        ]
        readme = fetch_readme(username, r["name"]) if with_readmes else None
        signals.append(
            RepoSignal(
                name=r["name"],
                description=r.get("description") or None,
                url=r.get("url", ""),
                homepage=r.get("homepageUrl") or None,
                primary_language=lang_obj.get("name") if lang_obj else None,
                languages=[x for x in languages if x],
                topics=_topics(r),
                stars=r.get("stargazerCount", 0),
                forks=r.get("forkCount", 0),
                is_fork=r.get("isFork", False),
                is_archived=r.get("isArchived", False),
                created_at=r.get("createdAt"),
                updated_at=r.get("updatedAt"),
                readme=readme,
            )
        )
    return signals


def language_histogram(signals: list[RepoSignal]) -> dict[str, int]:
    """Count primary languages across repos — a quick skills signal."""
    hist: dict[str, int] = {}
    for s in signals:
        if s.primary_language:
            hist[s.primary_language] = hist.get(s.primary_language, 0) + 1
    return dict(sorted(hist.items(), key=lambda kv: kv[1], reverse=True))
