"""Typed configuration, loaded from environment / .env.

Secrets (API keys, mail creds) live in the environment — never in code or the DB.
See config/.env.example for every variable.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root = two levels up from this file (piperline/config.py -> repo/)
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PROFILE_DIR = DATA_DIR / "profile"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / "config" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- LLM (model & gateway agnostic, via LiteLLM) ---------------------
    # `llm_model` uses LiteLLM naming, e.g. "claude-opus-4-8", "gpt-4o",
    # "gemini/gemini-1.5-pro", or "openai/<model>" against a custom base_url.
    llm_model: str = Field(default="claude-opus-4-8")
    llm_api_key: str | None = Field(default=None)
    llm_api_base: str | None = Field(default=None)  # custom gateway endpoint
    llm_temperature: float = Field(default=0.4)

    # --- storage ---------------------------------------------------------
    db_path: Path = Field(default=DATA_DIR / "piperline.db")

    # --- matching --------------------------------------------------------
    fit_threshold: float = Field(default=0.6)  # blended (LLM) score cutoff
    # deterministic-only runs (no LLM key) score systematically lower, so they
    # use a gentler cutoff as a rough prefilter.
    deterministic_fit_threshold: float = Field(default=0.25)

    # --- safety switches (autopilot OFF by default, per stage) -----------
    autopilot_apply: bool = Field(default=False)
    autopilot_outreach: bool = Field(default=False)
    max_outreach_per_day: int = Field(default=20)

    # --- outreach email (SMTP or Gmail API) ------------------------------
    smtp_host: str | None = Field(default=None)  # e.g. smtp.gmail.com
    smtp_port: int = Field(default=587)
    smtp_user: str | None = Field(default=None)  # your email
    smtp_pass: str | None = Field(default=None)  # app password for Gmail

    # --- aggregator defaults ---------------------------------------------
    default_country_indeed: str = Field(default="usa")
    proxies: str | None = Field(default=None)  # comma-separated


def get_settings() -> Settings:
    return Settings()
