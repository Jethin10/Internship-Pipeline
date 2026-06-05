"""Answer application screening questions from the Profile — or escalate.

Free-text and dropdown questions ("Why do you want to work here?", "Years of
Python?", "Are you authorized to work in X?") are answered from real profile
facts via the LLM. Anything the profile can't ground, or anything legally/ethically
sensitive, is ESCALATED to the human rather than guessed — wrong answers on
authorization/sponsorship/demographic questions are worse than a blank.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from piperline.common import Profile
from piperline.config import Settings

# Questions we never auto-answer — always hand to the human.
_ESCALATE_PATTERNS = [
    r"sponsor", r"visa", r"authorized to work", r"work authorization",
    r"require .* sponsorship", r"security clearance", r"felon|convicted|criminal",
    r"disability", r"veteran", r"gender|race|ethnicity|hispanic",
    r"salary|compensation expectation|expected pay", r"notice period",
    r"willing to relocate",  # often consequential; let the human decide
]
_ESCALATE_RE = re.compile("|".join(_ESCALATE_PATTERNS), re.IGNORECASE)


@dataclass
class Answer:
    question: str
    answer: str | None
    escalate: bool
    reason: str = ""


def _should_escalate(question: str) -> bool:
    return bool(_ESCALATE_RE.search(question or ""))


_SYSTEM = """\
You answer a job application question using ONLY facts from the candidate's
profile. Be concise and truthful. If the profile does not contain enough
information to answer factually, respond with exactly: ESCALATE.
Never invent experience, numbers, or credentials. Return STRICT JSON:
{"answer": "<text or ESCALATE>", "confidence": <0..1>}"""


def answer_question(
    question: str,
    profile: Profile,
    *,
    settings: Settings,
    options: list[str] | None = None,
    min_confidence: float = 0.55,
) -> Answer:
    """Answer one question, or flag it for human review."""
    if _should_escalate(question):
        return Answer(question, None, escalate=True, reason="sensitive/legal question")

    from piperline import llm

    opt_txt = f"\nChoose from these options exactly: {options}" if options else ""
    user = (
        f"QUESTION: {question}{opt_txt}\n\n"
        f"CANDIDATE PROFILE (JSON):\n{profile.model_dump_json()}"
    )
    try:
        data = llm.complete_json(
            [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}],
            settings=settings,
        )
    except Exception as e:
        return Answer(question, None, escalate=True, reason=f"LLM error: {type(e).__name__}")

    ans = str(data.get("answer", "")).strip()
    conf = float(data.get("confidence", 0.0))
    if not ans or ans.upper() == "ESCALATE" or conf < min_confidence:
        return Answer(question, None, escalate=True, reason=f"low confidence ({conf})")
    if options and ans not in options:
        # LLM didn't pick a valid option — don't guess.
        return Answer(question, None, escalate=True, reason="answer not in allowed options")
    return Answer(question, ans, escalate=False)
