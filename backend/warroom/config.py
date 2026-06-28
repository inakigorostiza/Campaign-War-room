"""Configuration loading from .env / environment (mirrors the slidegen Settings pattern)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Backend root = parent of the warroom/ package dir.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    anthropic_api_key: str
    claude_model: str
    source: str               # "seed" | "coupler"
    coupler_access_token: str | None
    db_path: Path
    refresh_seconds: int

    @classmethod
    def load(cls, env_path: str | None = None) -> "Settings":
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv(_BACKEND_ROOT / ".env")

        source = os.getenv("WARROOM_SOURCE", "seed").strip().lower()

        # Resolve the DB path relative to the backend root if not absolute.
        raw_db = os.getenv("WARROOM_DB", "data/sample_metrics.db")
        db_path = Path(raw_db)
        if not db_path.is_absolute():
            db_path = _BACKEND_ROOT / db_path

        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-opus-4-8"),
            source=source,
            coupler_access_token=os.getenv("COUPLER_ACCESS_TOKEN") or None,
            db_path=db_path,
            refresh_seconds=int(os.getenv("REFRESH_SECONDS", "20")),
        )

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)
