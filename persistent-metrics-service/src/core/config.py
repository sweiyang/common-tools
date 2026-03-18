"""
Load application configuration from a YAML file.

Config file path: set CONFIG_PATH env var, or default to config.yaml in current
working directory. If the file is missing, defaults are used so the app can run
without a config file.
"""

import os
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


def _config_path() -> Path:
    env_path = os.getenv("CONFIG_PATH")
    if env_path:
        return Path(env_path)
    candidates = [
        Path("config.yaml"),
        Path(__file__).resolve().parents[2] / "config.yaml",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return Path("config.yaml")


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    if yaml is None:
        raise RuntimeError("PyYAML is required. Install with: pip install pyyaml")
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return data if isinstance(data, dict) else {}


def _get(raw: dict, key: str, default: Any = None) -> Any:
    """Get nested key like 'database.prod.host' from a dict."""
    keys = key.split(".")
    v = raw
    for k in keys:
        if isinstance(v, dict) and k in v:
            v = v[k]
        else:
            return default
    return v


class Config:
    _raw: dict
    _path: Path

    def __init__(self) -> None:
        self._path = _config_path()
        self._raw = _load_yaml(self._path)

    # --- Environment ---
    @property
    def app_env(self) -> str:
        return os.getenv("APP_ENV", "prod").lower()

    # --- Database ---
    def _db_env(self) -> str:
        return self.app_env

    @property
    def database_host(self) -> str:
        return _get(self._raw, f"database.{self._db_env()}.host") or "localhost"

    @property
    def database_port(self) -> int:
        return int(_get(self._raw, f"database.{self._db_env()}.port") or 5433)

    @property
    def database_name(self) -> str:
        return _get(self._raw, f"database.{self._db_env()}.dbname") or "yugabyte"

    @property
    def database_user(self) -> str:
        return _get(self._raw, f"database.{self._db_env()}.user") or "yugabyte"

    @property
    def database_credential(self) -> str:
        return _get(self._raw, f"database.{self._db_env()}.credential") or "yugabyte"

    @property
    def database_schema(self) -> Optional[str]:
        return _get(self._raw, f"database.{self._db_env()}.schema")

    # --- Auth ---
    @property
    def auth_api_key(self) -> str:
        return _get(self._raw, "auth.api_key") or "change-me-to-a-real-secret"

    # --- Server ---
    @property
    def server_host(self) -> str:
        return _get(self._raw, "server.host") or "0.0.0.0"

    @property
    def server_port(self) -> int:
        return int(_get(self._raw, "server.port") or 8000)

    # --- Logging ---
    @property
    def log_level(self) -> str:
        return _get(self._raw, "logging.level") or "INFO"

    @property
    def log_format(self) -> str:
        return _get(self._raw, "logging.format") or "{time:YYYY-MM-DD HH:mm:ss} - {extra[name]} - {level} - {message}"


_config: Optional[Config] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config
