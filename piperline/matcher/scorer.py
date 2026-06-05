"""Score how well a job fits the user — deterministic signals + LLM nuance.

Two layers:
  1. A cheap, transparent deterministic score from skill/keyword overlap. Always
     available, no API key, used as a prefilter and a sanity check on the LLM.
  2. An optional LLM judgement that reads the JD against the profile and returns
     a 0-1 fit with a short rationale, catching nuance keywords miss.

The public `score_job` blends them; callers can stay deterministic-only by
passing use_llm=False (e.g. when no key is configured).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from piperline.common import JobPost, Profile
from piperline.config import Settings

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.\-]{1,}")


@dataclass
class FitResult:
    score: float  # 0..1
    rationale: str
    matched_skills: list[str]
    missing_keywords: list[str]
    deterministic_score: float
    llm_score: float | None = None


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD.finditer(text or "")}


def _profile_terms(profile: Profile) -> set[str]:
    """All terms the profile can legitimately match a JD on."""
    terms: set[str] = set()
    terms |= {s.name.lower() for s in profile.skills}
    for e in profile.experience:
        terms |= {t.lower() for t in e.tech}
    for pr in profile.projects:
        terms |= {t.lower() for t in pr.tech}
    # multi-word skills also contribute their individual words
    for s in profile.skills:
        terms |= _tokens(s.name)
    return {t for t in terms if len(t) > 1}


def deterministic_score(job: JobPost, profile: Profile) -> FitResult:
    """Skill/keyword overlap between the JD and the profile. No LLM."""
    jd_tokens = _tokens(job.title) | _tokens(job.description)
    p_terms = _profile_terms(profile)

    matched = sorted(t for t in p_terms if t in jd_tokens)

    # Which profile skills (by full name) appear in the JD?
    matched_skills = sorted(
        s.name for s in profile.skills
        if s.name.lower() in jd_tokens
        or all(w in jd_tokens for w in _tokens(s.name))
    )

    # Coverage = fraction of the user's skills the JD mentions (capped), plus a
    # bump for raw overlap volume so dense matches rank above sparse ones.
    skill_cov = len(matched_skills) / max(6, len(profile.skills))
    overlap_signal = min(1.0, len(matched) / 12.0)
    score = round(min(1.0, 0.6 * skill_cov + 0.4 * overlap_signal), 3)

    # Surface a few JD keywords the profile doesn't cover (gaps worth knowing).
    stop = _STOPWORDS
    jd_keywords = [t for t in jd_tokens if t not in stop and len(t) > 3]
    missing = sorted(set(jd_keywords) - p_terms)[:12]

    rationale = (
        f"Matched {len(matched_skills)} skills "
        f"({', '.join(matched_skills[:8]) or 'none'}); "
        f"{len(matched)} total term overlaps with the JD."
    )
    return FitResult(
        score=score,
        rationale=rationale,
        matched_skills=matched_skills,
        missing_keywords=missing,
        deterministic_score=score,
    )


_STOPWORDS = {
    "the", "and", "for", "with", "you", "our", "are", "will", "your", "have",
    "this", "that", "from", "their", "they", "what", "who", "all", "can", "job",
    "work", "team", "role", "company", "experience", "years", "ability", "strong",
    "looking", "join", "including", "etc", "such", "able", "must", "should",
    "responsibilities", "requirements", "skills", "plus", "good", "great", "new",
}


_LLM_SYSTEM = """\
You assess how well a candidate fits a job. Be honest and calibrated: a strong
fit is 0.8+, a plausible stretch 0.5-0.7, a poor fit below 0.4. Judge on real
skill/domain overlap and seniority fit, not enthusiasm. Return STRICT JSON only."""


def _profile_brief(profile: Profile) -> str:
    skills = ", ".join(s.name for s in profile.skills)
    projects = "; ".join(f"{p.title} ({', '.join(p.tech[:4])})" for p in profile.projects)
    roles = "; ".join(f"{e.role} @ {e.organization}" for e in profile.experience)
    return (
        f"Headline: {profile.basics.headline}\n"
        f"Summary: {profile.summary}\n"
        f"Roles: {roles}\n"
        f"Skills: {skills}\n"
        f"Projects: {projects}"
    )


def llm_score(job: JobPost, profile: Profile, *, settings: Settings) -> tuple[float, str]:
    """Ask the LLM for a calibrated 0-1 fit and a one-sentence rationale."""
    from piperline import llm

    instructions = (
        'Return JSON: {"score": <0..1 float>, "rationale": "<one sentence>", '
        '"concerns": ["<gap>", ...]}\n\n'
        f"CANDIDATE:\n{_profile_brief(profile)}\n\n"
        f"JOB:\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Location: {job.location} (remote={job.is_remote})\n"
        f"Description:\n{job.description[:4000]}"
    )
    data = llm.complete_json(
        [
            {"role": "system", "content": _LLM_SYSTEM},
            {"role": "user", "content": instructions},
        ],
        settings=settings,
    )
    score = float(data.get("score", 0.0))
    rationale = str(data.get("rationale", "")).strip()
    concerns = data.get("concerns") or []
    if concerns:
        rationale += " Concerns: " + "; ".join(str(c) for c in concerns[:3])
    return max(0.0, min(1.0, score)), rationale


def score_job(
    job: JobPost,
    profile: Profile,
    *,
    settings: Settings,
    use_llm: bool = True,
) -> FitResult:
    """Blend deterministic overlap with LLM judgement (when available).

    Falls back to the deterministic score if use_llm is False or the LLM errors,
    so scoring never hard-fails the pipeline.
    """
    det = deterministic_score(job, profile)
    if not use_llm:
        return det

    try:
        score_llm, rationale = llm_score(job, profile, settings=settings)
    except Exception as e:
        det.rationale += f" (LLM scoring unavailable: {type(e).__name__})"
        return det

    # Weight the LLM higher — it reads nuance — but keep the deterministic floor
    # as a guard against hallucinated enthusiasm.
    blended = round(0.65 * score_llm + 0.35 * det.deterministic_score, 3)
    det.score = blended
    det.llm_score = score_llm
    det.rationale = rationale + f" [keyword match: {det.deterministic_score}]"
    return det
