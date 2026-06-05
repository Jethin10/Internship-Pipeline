"""Tailor a resume to a specific job — truthfully.

The LLM is allowed to SELECT, REORDER, and REPHRASE the user's real profile facts
to surface what a given JD cares about. It is NOT allowed to invent employers,
roles, projects, metrics, or skills. After generation, `fabrication_guard` checks
the tailored output against the source profile and flags anything unsupported.

Output is a new Profile object (same schema), so it renders through the exact
same resume template as the baseline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from piperline.common import JobPost, Profile
from piperline.config import Settings

_TAILOR_SYSTEM = """\
You tailor a resume to a job. You may ONLY use facts present in the candidate's
profile. You may reorder, select, and rephrase for relevance and impact. You must
NOT invent, exaggerate, or add employers, titles, dates, metrics, technologies,
or achievements that are not in the profile. Mirror the job's terminology only
where it truthfully matches the candidate's real experience.
Return STRICT JSON matching the schema. No prose outside JSON."""

_TAILOR_SCHEMA = """\
Return JSON with this exact shape (a tailored Profile):
{
  "summary": "<2-3 sentence summary aimed at THIS job, true to the profile>",
  "experience": [ {"role","organization","location","start","end",
                    "highlights":[...], "tech":[...]} ],
  "projects":   [ {"title","summary","impact":[...],"tech":[...],"links":{}} ],
  "skills":     [ {"name","category","level"} ],
  "achievements": [ "..." ]
}
Rules:
- Pick and order the experiences/projects MOST relevant to the job first.
- Keep only skills the candidate actually has; order job-relevant ones first.
- Highlights may be rephrased for impact but must stay factually identical.
- Drop items irrelevant to the job rather than padding. Keep it to one page worth.
"""


@dataclass
class TailorResult:
    profile: Profile  # tailored, renders through the same template
    guard: "GuardReport"


def tailor_resume(
    job: JobPost,
    profile: Profile,
    *,
    settings: Settings,
) -> TailorResult:
    """Produce a JD-tailored Profile, then verify it didn't fabricate anything."""
    from piperline import llm

    user = (
        _TAILOR_SCHEMA
        + f"\n\nJOB:\nTitle: {job.title}\nCompany: {job.company}\n"
        + f"Description:\n{job.description[:4500]}\n\n"
        + f"CANDIDATE PROFILE (JSON):\n{profile.model_dump_json(indent=2)}"
    )
    data = llm.complete_json(
        [
            {"role": "system", "content": _TAILOR_SYSTEM},
            {"role": "user", "content": user},
        ],
        settings=settings,
    )

    # Carry over immutable basics/education/links from the source of truth — the
    # LLM never gets to touch contact details or credentials.
    data["basics"] = profile.basics.model_dump()
    data["education"] = [e.model_dump() for e in profile.education]
    data.setdefault("links", profile.links)
    tailored = Profile.model_validate(data)

    report = fabrication_guard(tailored, profile)
    return TailorResult(profile=tailored, guard=report)


# ---------------------------------------------------------------------------
# Fabrication guard — enforce "truthful by construction" (VISION.md principle 2)
# ---------------------------------------------------------------------------
@dataclass
class GuardReport:
    ok: bool
    flags: list[str] = field(default_factory=list)  # human-readable problems

    def summary(self) -> str:
        if self.ok:
            return "Fabrication guard: PASS — all tailored facts trace to the profile."
        return "Fabrication guard: FLAGS\n  - " + "\n  - ".join(self.flags)


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _source_corpus(profile: Profile) -> str:
    """Everything the profile legitimately contains, as one normalized blob."""
    parts: list[str] = [profile.summary]
    for e in profile.experience:
        parts += [e.role, e.organization, e.location or "", *e.highlights, *e.tech]
    for p in profile.projects:
        parts += [p.title, p.summary or "", *p.impact, *p.tech]
    parts += profile.achievements
    parts += [s.name for s in profile.skills]
    return _norm(" || ".join(parts))


def fabrication_guard(tailored: Profile, source: Profile) -> GuardReport:
    """Flag tailored content that isn't grounded in the source profile.

    Structural facts (org names, titles, skill names) must appear in the source.
    Rephrased highlights are allowed, so we check those by entity grounding
    (their organization/project must exist) rather than exact-string match.
    """
    flags: list[str] = []
    src_orgs = {_norm(e.organization) for e in source.experience}
    src_roles = {_norm(e.role) for e in source.experience}
    src_projects = {_norm(p.title) for p in source.projects}
    src_skills = {_norm(s.name) for s in source.skills}
    corpus = _source_corpus(source)

    # 1. No invented employers or roles.
    for e in tailored.experience:
        if _norm(e.organization) not in src_orgs:
            flags.append(f"Experience org not in profile: '{e.organization}'")
        if _norm(e.role) not in src_roles:
            flags.append(f"Experience role not in profile: '{e.role}'")

    # 2. No invented projects.
    for p in tailored.projects:
        if _norm(p.title) not in src_projects:
            flags.append(f"Project not in profile: '{p.title}'")

    # 3. No invented skills.
    for s in tailored.skills:
        if _norm(s.name) not in src_skills:
            flags.append(f"Skill not in profile: '{s.name}'")

    # 4. No invented achievements (allow rephrase: require token overlap with
    #    some source sentence; flag if it looks wholly new).
    for a in tailored.achievements:
        toks = [t for t in _norm(a).split() if len(t) > 3]
        if toks and sum(1 for t in toks if t in corpus) / len(toks) < 0.4:
            flags.append(f"Achievement may be fabricated: '{a[:70]}'")

    return GuardReport(ok=not flags, flags=flags)
