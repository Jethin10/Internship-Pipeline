"""The Master Profile — the single source of truth about the user.

Every tailored document is *derived* from this. Tailoring may select and reframe
these facts, but must never invent ones not present here (VISION.md principle #2,
enforced by the fabrication guard in the matcher).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Basics(BaseModel):
    name: str
    email: str
    phone: str | None = None
    location: str | None = None
    headline: str | None = None  # e.g. "CS student • backend + ML"


class Education(BaseModel):
    institution: str
    degree: str | None = None
    field: str | None = None
    start: str | None = None
    end: str | None = None  # may be "expected 2027"
    gpa: str | None = None
    highlights: list[str] = Field(default_factory=list)


class Experience(BaseModel):
    role: str
    organization: str
    location: str | None = None
    start: str | None = None
    end: str | None = None  # "present" allowed
    highlights: list[str] = Field(default_factory=list)  # impact bullets
    tech: list[str] = Field(default_factory=list)


class Project(BaseModel):
    title: str
    summary: str | None = None
    impact: list[str] = Field(default_factory=list)  # what it achieved
    tech: list[str] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)  # repo, demo, ...


class Skill(BaseModel):
    name: str
    category: str | None = None  # "language" | "framework" | "tool" | ...
    level: str | None = None  # "expert" | "proficient" | "familiar"


class Profile(BaseModel):
    basics: Basics
    summary: str = ""
    education: list[Education] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    links: dict[str, str] = Field(default_factory=dict)  # github, portfolio, ...

    def skill_names(self) -> set[str]:
        return {s.name.lower() for s in self.skills}
