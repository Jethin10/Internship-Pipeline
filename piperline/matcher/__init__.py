"""Part C (start) — Master Profile loader.

Loads the user's Master Profile from data/profile/profile.yaml and validates it
into the Profile contract. This is the single source of truth every tailored
document derives from.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from piperline.common import Profile
from piperline.config import PROFILE_DIR

DEFAULT_PROFILE_PATH = PROFILE_DIR / "profile.yaml"


def load_profile(path: Path | None = None) -> Profile:
    """Read and validate the Master Profile. Raises if missing or invalid."""
    p = path or DEFAULT_PROFILE_PATH
    if not p.exists():
        raise FileNotFoundError(
            f"No profile found at {p}. Copy data/profile/profile.example.yaml "
            "to profile.yaml and fill in your details."
        )
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return Profile.model_validate(data)


__all__ = ["load_profile", "DEFAULT_PROFILE_PATH"]
