"""Configuration, loaded from the environment (and an optional .env file).

The API key is NEVER read from a file that is committed. `.env` is gitignored.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
DEFAULT_CACHE_DIR = PROJECT_DIR / "data" / "cache"
WEB_DIR = PROJECT_DIR / "web"


def load_dotenv(path: Path | None = None) -> None:
    """Read KEY=VALUE lines from .env into os.environ without overwriting."""
    path = path or (PROJECT_DIR / ".env")
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    api_key: str
    transport: str           # "auto" | "native" | "apilayer"
    api_version: str         # "v1" | "v2" (native transport only)
    cache_dir: Path
    cache_ttl_seconds: int
    request_timeout: int
    host: str
    port: int

    @property
    def has_key(self) -> bool:
        return bool(self.api_key)


def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        api_key=os.environ.get("MARKETSTACK_API_KEY", "").strip(),
        transport=os.environ.get("MARKETSTACK_TRANSPORT", "auto").strip().lower(),
        api_version=os.environ.get("MARKETSTACK_API_VERSION", "v1").strip().lower(),
        cache_dir=Path(os.environ.get("MARKETLAB_CACHE_DIR", str(DEFAULT_CACHE_DIR))),
        cache_ttl_seconds=int(os.environ.get("MARKETLAB_CACHE_TTL", "43200")),
        request_timeout=int(os.environ.get("MARKETLAB_HTTP_TIMEOUT", "30")),
        host=os.environ.get("MARKETLAB_HOST", "127.0.0.1"),
        port=int(os.environ.get("MARKETLAB_PORT", "8787")),
    )
