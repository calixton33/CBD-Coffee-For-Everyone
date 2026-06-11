from __future__ import annotations

import os
from dataclasses import dataclass, field


DEFAULT_DATABASE_URL = "sqlite:///./coffee_cbd.db"
DEFAULT_SECRET_KEY = "dev-secret-change-me"
PLACEHOLDER_SECRET_KEYS = {
    DEFAULT_SECRET_KEY,
    "change-this-before-production",
    "replace-with-a-long-random-local-secret",
}


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _runtime_env() -> str:
    return os.getenv("APP_ENV") or os.getenv("VERCEL_ENV") or "development"


def _normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value.removeprefix("postgres://")
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value.removeprefix("postgresql://")
    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = field(
        default_factory=lambda: os.getenv("APP_NAME", "CBD Coffee Price Directory")
    )
    environment: str = field(default_factory=_runtime_env)
    database_url: str = field(
        default_factory=lambda: _normalize_database_url(
            os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
        )
    )
    secret_key: str = field(
        default_factory=lambda: os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    )
    auto_seed: bool = field(default_factory=lambda: _as_bool(os.getenv("AUTO_SEED"), True))
    seed_demo_editors: bool = field(
        default_factory=lambda: _as_bool(os.getenv("SEED_DEMO_EDITORS"), False)
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _as_list(
            os.getenv("CORS_ORIGINS"),
            ("http://127.0.0.1:8001", "http://localhost:8001"),
        )
    )

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    def __post_init__(self) -> None:
        object.__setattr__(self, "database_url", _normalize_database_url(self.database_url))

        if self.is_production:
            if not self.secret_key.strip() or self.secret_key in PLACEHOLDER_SECRET_KEYS:
                raise RuntimeError(
                    "Set a strong SECRET_KEY before running in production."
                )
            if self.database_url == DEFAULT_DATABASE_URL or self.database_url.startswith(
                "sqlite"
            ):
                raise RuntimeError(
                    "Set DATABASE_URL to a persistent external database before "
                    "running in production."
                )


settings = Settings()
