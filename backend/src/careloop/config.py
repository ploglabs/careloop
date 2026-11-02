"""Runtime settings, read once from the environment (and `.env` if present)."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./careloop.db")
    public_web_url: str = os.getenv("PUBLIC_WEB_URL", "http://localhost:3000")

    # Gnani (Prisma STT + Timbre TTS)
    gnani_api_key: str | None = os.getenv("GNANI_API_KEY")
    stt_model: str = os.getenv("CARELOOP_STT_MODEL", "prisma-v2.5")
    tts_model: str = os.getenv("CARELOOP_TTS_MODEL", "timbre-v2.5")

    # Dialogue LLM: any OpenAI-compatible chat completions endpoint (DeepInfra by default)
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or os.getenv("DEEPINFRA_API_KEY")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.deepinfra.com/v1/openai")
    llm_model: str = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V4-Flash")
    # Hybrid models think before answering unless told not to; a phone call can't wait for that.
    # Empty sends nothing, for providers that reject the field.
    llm_reasoning_effort: str = os.getenv("LLM_REASONING_EFFORT", "none")
    # End-of-call second opinion on urgency. It can only raise the level.
    llm_review_enabled: bool = _bool("CARELOOP_LLM_REVIEW", True)

    # Call handling
    max_call_seconds: int = int(os.getenv("CARELOOP_MAX_CALL_SECONDS", "360"))
    ring_timeout_seconds: int = int(os.getenv("CARELOOP_RING_TIMEOUT_SECONDS", "90"))
    retry_interval_minutes: int = int(os.getenv("CARELOOP_RETRY_INTERVAL_MINUTES", "120"))
    max_attempts: int = int(os.getenv("CARELOOP_MAX_ATTEMPTS", "3"))
    scheduler_enabled: bool = _bool("CARELOOP_SCHEDULER", True)
    scheduler_tick_seconds: int = int(os.getenv("CARELOOP_SCHEDULER_TICK_SECONDS", "20"))
    adherence_miss_threshold: int = int(os.getenv("CARELOOP_ADHERENCE_MISS_THRESHOLD", "2"))

    # Audio is never stored unless explicitly enabled (DPDP data minimisation).
    store_audio: bool = _bool("CARELOOP_STORE_AUDIO", False)

    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    )

    @property
    def llm_extra_body(self) -> dict:
        return {"reasoning_effort": self.llm_reasoning_effort} if self.llm_reasoning_effort else {}

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key)

    @property
    def voice_enabled(self) -> bool:
        return bool(self.gnani_api_key and self.llm_api_key)


settings = Settings()
