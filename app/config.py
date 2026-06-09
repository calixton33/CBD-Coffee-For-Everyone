from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_list(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "CBD Coffee Price Directory")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./coffee_cbd.db")
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-change-me")
    auto_seed: bool = _as_bool(os.getenv("AUTO_SEED"), True)
    seed_demo_editors: bool = _as_bool(os.getenv("SEED_DEMO_EDITORS"), False)
    cors_origins: tuple[str, ...] = _as_list(
        os.getenv("CORS_ORIGINS"),
        ("http://127.0.0.1:8001", "http://localhost:8001"),
    )

    def __post_init__(self) -> None:
        if os.getenv("APP_ENV", "development").lower() == "production":
            if self.secret_key in {"dev-secret-change-me", "change-this-before-production"}:
                raise RuntimeError("Set a strong SECRET_KEY before running in production.")


settings = Settings()
