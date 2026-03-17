from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel


class DatabaseConfig(BaseModel):
    url: str = "postgresql+asyncpg://yugabyte:yugabyte@localhost:5433/yugabyte"


class AuthConfig(BaseModel):
    api_key: str = "change-me-to-a-real-secret"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class Settings(BaseModel):
    database: DatabaseConfig = DatabaseConfig()
    auth: AuthConfig = AuthConfig()
    server: ServerConfig = ServerConfig()


def _find_config_path() -> Path | None:
    env_path = os.environ.get("CONFIG_PATH")
    if env_path:
        return Path(env_path)
    candidates = [
        Path("config.yaml"),
        Path(__file__).resolve().parents[2] / "config.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


@lru_cache
def get_settings() -> Settings:
    path = _find_config_path()
    if path is None:
        return Settings()
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return Settings(**raw)
