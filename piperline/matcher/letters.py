"""Draft a cover letter and a short outreach email — grounded in the profile.

Same truthfulness rule as resume tailoring: these reference only real facts.
Output is plain text (cover letter) and a subject+body (outreach), ready for
review before anything is sent.
"""
from __future__ import annotations

from dataclasses import dataclass

from piperline.common import JobPost, Profile
from piperline.config import Settings

_CL_SYSTEM = """\
You write cover letters that sound like a real 18-year-old CS student who builds
products for fun and wins hackathons — NOT a corporate template.

VOICE RULES:
- NEVER start a sentence with "I" more than once per paragraph
- NEVER open with "I am writing to apply" or "I am excited about"
- Open with a hook: a quick story, a bold claim about what you've built, or a
  specific connection to what the company does
- Use short sentences. Fragments are fine. This isn't an essay.
- Show, don't tell: "trained a YOLOv8 model that hit 0.914 precision" beats
  "I am proficient in machine learning"
- Pick 2-3 things from the profile that match THIS job specifically — don't
  dump every achievement
- End with what you'll actually DO for them, not "I look forward to hearing from you"
- Sound like a real human — slightly informal, confident but not arrogant
- 3-4 short paragraphs MAX
- Use ONLY real facts from the profile. Never invent.

BAD (don't do this):
  "I am a highly motivated CS student with experience in AI/ML..."
  "My skills in Python and TypeScript make me a strong candidate..."

GOOD (do this):
  "Last month I trained a YOLOv8 model to detect safety hazards in a space
  station simulation — 0.914 precision, deployed in a Streamlit app the same
  day. That's the kind of work I want to do at [Company]."
"""

_OUTREACH_SYSTEM = """\
You write SHORT, personal outreach emails that sound like a real person typed
them in 2 minutes — not a marketing team drafted them for an hour.

VOICE RULES:
- 4-6 sentences MAX. Shorter is better.
- Open with something specific about the COMPANY (a product, a recent post,
  something they shipped) — proves you're not mass-emailing
- ONE concrete thing about the candidate that connects to this specific role
- No "I hope this email finds you well"
- No "I am reaching out to express my interest"
- No bullet points. No headers. Just a few sentences.
- End with a casual ask, not a formal "I would welcome the opportunity"
- Sound like a student reaching out to someone they respect, not a salesperson
- The email will automatically have LinkedIn + GitHub links appended at the bottom,
  so DON'T manually paste URLs in the body — just reference that you've included
  them (e.g. "linked below" or "my resume is attached")
- A resume PDF will be automatically attached — mention it briefly (e.g. "I've
  attached my resume" or "resume attached for more detail")
- Use ONLY real facts from the profile. Never invent.

BAD (don't do this):
  "Dear Hiring Manager, I am writing to express my strong interest in the
  Software Engineer Intern position at your esteemed organization..."

GOOD (do this):
  "Hey [Name], saw your post about [thing] — that's exactly the kind of work
  I've been doing with [specific project]. I'm a first-year CS student who's
  shipped [concrete thing]. Would love to chat for 10 minutes if you have
  time this week."

Return STRICT JSON: {"subject","body"}.
"""


def draft_cover_letter(job: JobPost, profile: Profile, *, settings: Settings) -> str:
    from piperline import llm

    user = (
        f"CANDIDATE PROFILE (JSON):\n{profile.model_dump_json(indent=2)}\n\n"
        f"JOB:\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Description:\n{job.description[:4000]}\n\n"
        f"Write the cover letter body (no address block). Sign as {profile.basics.name}."
    )
    return llm.complete(
        [
            {"role": "system", "content": _CL_SYSTEM},
            {"role": "user", "content": user},
        ],
        settings=settings,
    ).strip()


@dataclass
class OutreachDraft:
    subject: str
    body: str


def draft_outreach(
    job: JobPost,
    profile: Profile,
    *,
    settings: Settings,
    contact_name: str | None = None,
) -> OutreachDraft:
    from piperline import llm

    greeting = f"Addressed to: {contact_name}" if contact_name else "Recipient name unknown — use a neutral greeting."
    user = (
        f"{greeting}\n\n"
        f"CANDIDATE: {profile.basics.name}\n{_brief(profile)}\n\n"
        f"JOB:\nTitle: {job.title}\nCompany: {job.company}\n"
        f"Description:\n{job.description[:3000]}"
    )
    data = llm.complete_json(
        [
            {"role": "system", "content": _OUTREACH_SYSTEM},
            {"role": "user", "content": user},
        ],
        settings=settings,
    )
    return OutreachDraft(
        subject=str(data.get("subject", f"Interest in {job.title}")).strip(),
        body=str(data.get("body", "")).strip(),
    )


def _brief(profile: Profile) -> str:
    skills = ", ".join(s.name for s in profile.skills[:10])
    projects = "; ".join(p.title for p in profile.projects[:4])
    links = []
    if profile.links:
        ln = profile.links.get("linkedin") if isinstance(profile.links, dict) else getattr(profile.links, "linkedin", None)
        gh = profile.links.get("github") if isinstance(profile.links, dict) else getattr(profile.links, "github", None)
        if ln:
            links.append(f"LinkedIn: {ln}")
        if gh:
            links.append(f"GitHub: {gh}")
    links_str = "\n" + "\n".join(links) if links else ""
    return f"Headline: {profile.basics.headline}\nSkills: {skills}\nProjects: {projects}{links_str}"
