"""Central paths and validated configuration for the standalone system."""
import os
from pathlib import Path
from typing import Literal
from dotenv import load_dotenv
from pydantic import BaseModel, Field, SecretStr

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / ".runtime"
RUNS = ROOT / "artifacts" / "runs"
load_dotenv(ROOT / ".env")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(RUNTIME / "browsers"))
os.environ.setdefault("BROWSER_USE_CONFIG_DIR", str(RUNTIME / "browser-use"))
os.environ.setdefault("XDG_CACHE_HOME", str(RUNTIME / "cache"))


class Settings(BaseModel):
    provider: Literal["google", "gemini", "browser-use", "openai"] = "google"
    model: str = "gemini-3.5-flash-lite"
    google_api_key: SecretStr = SecretStr("")
    browser_use_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    openai_base_url: str = ""
    max_pages: int = Field(default=6, ge=1, le=20)
    max_probes: int = Field(default=6, ge=0, le=20)
    llm_timeout: int = Field(default=90, ge=10, le=300)

    @classmethod
    def from_env(cls):
        return cls(provider=os.getenv("MODEL_PROVIDER", "google").strip().lower(),
            model=os.getenv("MODEL_NAME", "gemini-3.5-flash-lite").strip(),
            google_api_key=os.getenv("GOOGLE_API_KEY", ""),
            browser_use_api_key=os.getenv("BROWSER_USE_API_KEY", ""),
            openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            openai_base_url=os.getenv("OPENAI_BASE_URL", ""),
            max_pages=os.getenv("MAX_PAGES", "6"), max_probes=os.getenv("MAX_PROBES", "6"),
            llm_timeout=os.getenv("LLM_TIMEOUT_SECONDS", "90"))
