"""Central configuration. Every value comes from environment variables (backend/.env)."""
import logging
import os
import secrets
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("ava.config")


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32:
        logger.warning(
            "JWT_SECRET is missing or shorter than 32 characters. "
            "Using a random secret: admin tokens become invalid on every restart."
        )
        return secrets.token_urlsafe(48)
    return secret


@dataclass(frozen=True)
class Settings:
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))

    # Database
    db_user: str = field(default_factory=lambda: os.getenv("DB_USER", ""))
    db_password: str = field(default_factory=lambda: os.getenv("DB_PASSWORD", ""))
    db_host: str = field(default_factory=lambda: os.getenv("DB_HOST", "localhost"))
    db_port: str = field(default_factory=lambda: os.getenv("DB_PORT", "3306"))
    db_name: str = field(default_factory=lambda: os.getenv("DB_NAME", ""))
    database_url_override: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))

    # Security
    jwt_secret: str = field(default_factory=_jwt_secret)
    jwt_expire_minutes: int = field(default_factory=lambda: _int("JWT_EXPIRE_MINUTES", 480))
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
        ]
    )
    admin_username: str = field(default_factory=lambda: os.getenv("ADMIN_USERNAME", ""))
    admin_password: str = field(default_factory=lambda: os.getenv("ADMIN_PASSWORD", ""))

    # Rate limits (requests per minute per client IP)
    rate_limit_chat_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_CHAT_PER_MINUTE", 30))
    rate_limit_login_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_LOGIN_PER_MINUTE", 5))
    rate_limit_booking_per_minute: int = field(default_factory=lambda: _int("RATE_LIMIT_BOOKING_PER_MINUTE", 10))

    # Local LLM (runs inside this process; no API, no external service)
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "none").strip().lower())
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "Qwen/Qwen2.5-0.5B-Instruct"))
    llm_device: str = field(default_factory=lambda: os.getenv("LLM_DEVICE", "auto").strip().lower())
    llm_cache_dir: str = field(default_factory=lambda: os.getenv("LLM_CACHE_DIR", ""))
    llm_threads: int = field(default_factory=lambda: _int("LLM_THREADS", 0))  # 0 = PyTorch default
    llm_max_new_tokens: int = field(default_factory=lambda: _int("LLM_MAX_NEW_TOKENS", 256))
    llm_temperature: float = field(default_factory=lambda: _float("LLM_TEMPERATURE", 0.0))
    llm_timeout_seconds: float = field(default_factory=lambda: _float("LLM_TIMEOUT_SECONDS", 45))
    llm_max_tool_rounds: int = field(default_factory=lambda: _int("LLM_MAX_TOOL_ROUNDS", 4))
    llm_history_messages: int = field(default_factory=lambda: _int("LLM_HISTORY_MESSAGES", 10))
    # hybrid = the intent model answers confident, short messages instantly; the LLM handles the rest.
    # always = every message goes to the LLM.
    llm_mode: str = field(default_factory=lambda: os.getenv("LLM_MODE", "hybrid").strip().lower())
    llm_route_confidence: float = field(default_factory=lambda: _float("LLM_ROUTE_CONFIDENCE", 0.70))
    llm_route_max_words: int = field(default_factory=lambda: _int("LLM_ROUTE_MAX_WORDS", 14))

    # Logging
    chat_debug_logs: bool = field(default_factory=lambda: _bool("CHAT_DEBUG_LOGS", False))

    # Startup
    run_migrations_on_startup: bool = field(default_factory=lambda: _bool("RUN_MIGRATIONS_ON_STARTUP", True))
    seed_on_startup: bool = field(default_factory=lambda: _bool("SEED_ON_STARTUP", True))

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider not in {"", "none", "off", "disabled"}


settings = Settings()
