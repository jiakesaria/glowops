"""Shared model configuration for the checker and Sylvia's improvement script."""

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field

ROOT = Path(__file__).resolve().parent


class ConfigurationError(ValueError):
    pass


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    provider: str = "deepseek"
    model_id: str = ""
    base_url: str = "https://api.deepseek.com"
    api_key: str = Field(default="", repr=False)
    root: Path = ROOT
    max_approved_lessons: int = Field(default=10, ge=0, le=10)
    max_json_retries: int = Field(default=2, ge=0, le=5)
    temperature: float = Field(default=0, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=256)
    timeout_seconds: float = Field(default=30, gt=0)


def get_config(*, provider: str | None = None, root: Path = ROOT) -> Settings:
    """Load repo .env, with process environment taking precedence; never print keys."""
    values = {**dotenv_values(root / ".env"), **os.environ}
    selected = (provider or values.get("MODEL") or "deepseek").strip().lower()
    if selected not in {"deepseek", "qwen"}:
        raise ConfigurationError("MODEL must be deepseek or qwen")
    prefix = selected.upper()
    base_url = (values.get(f"{prefix}_BASE_URL") or "").strip()
    if not base_url and selected == "deepseek":
        base_url = "https://api.deepseek.com"
    try:
        return Settings(
            provider=selected,
            model_id=(values.get(f"{prefix}_MODEL") or "").strip(),
            base_url=base_url,
            api_key=(values.get(f"{prefix}_API_KEY") or "").strip(),
            root=root.resolve(),
            max_approved_lessons=int(values.get("MAX_APPROVED_LESSONS") or 10),
            max_json_retries=int(values.get("MAX_JSON_RETRIES") or 2),
            temperature=float(values.get("TEMPERATURE") or 0),
            max_tokens=int(values.get("MAX_OUTPUT_TOKENS") or 4096),
            timeout_seconds=float(values.get("API_TIMEOUT_SECONDS") or 30),
        )
    except ValueError as exc:
        raise ConfigurationError("Invalid numeric model setting; check .env limits") from exc


def create_client(settings: Settings | None = None):
    """Return an OpenAI-compatible client. No network call is made here."""
    from openai import OpenAI

    settings = settings or get_config()
    prefix = settings.provider.upper()
    for name, value in (
        (f"{prefix}_API_KEY", settings.api_key),
        (f"{prefix}_MODEL", settings.model_id),
        (f"{prefix}_BASE_URL", settings.base_url),
    ):
        if not value:
            raise ConfigurationError(f"Set {name} in .env before running real mode")
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        max_retries=2,
    )
