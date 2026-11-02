"""Runtime settings, read once from the environment / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

load_dotenv(REPO_DIR / ".env")


def _flag(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.xai_api_key: str = os.getenv("XAI_API_KEY", "").strip()
        self.xai_base_url: str = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1").strip()
        self.xai_model: str = os.getenv("XAI_MODEL", "").strip()
        self.llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "8"))
        self.offline: bool = _flag("CLEARANCE_OFFLINE")
        self.token: str = os.getenv("CLEARANCE_TOKEN", "change-me")
        self.public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
        self.scenario: str = os.getenv("SCENARIO", "atl_arrivals_demo.json")
        self.demo_mode: bool = _flag("DEMO_MODE")
        self.db_path: Path = Path(os.getenv("CLEARANCE_DB", str(BACKEND_DIR / "clearance.db")))
        self.scenarios_dir: Path = BACKEND_DIR / "scenarios"
        self.fixtures_dir: Path = BACKEND_DIR / "fixtures"
        self.cache_dir: Path = BACKEND_DIR / "app" / "llm" / "cache"
        self.dropbox_dir: Path = Path(os.getenv("BOT_DROPBOX", str(REPO_DIR / "bot_dropbox")))

    @property
    def llm_enabled(self) -> bool:
        return bool(self.xai_api_key and self.xai_model) and not self.offline


settings = Settings()
