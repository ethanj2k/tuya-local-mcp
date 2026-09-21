"""Runtime configuration, all sourced from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Filenames the tinytuya wizard produces, in the order we prefer them.
# devices.json is the full account dump; snapshot.json additionally carries the
# IP addresses discovered during the wizard's scan.
CANDIDATE_FILENAMES = ("snapshot.json", "devices.json")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _search_paths() -> list[Path]:
    """Places to look for a device file when TUYA_DEVICES_FILE is unset."""
    roots = [Path.cwd(), Path.home(), Path.home() / ".tinytuya"]
    return [root / name for root in roots for name in CANDIDATE_FILENAMES]


@dataclass(frozen=True)
class Config:
    devices_file: Path | None
    read_only: bool
    connect_timeout: float
    cache_ttl: float
    discovery_timeout: float

    @classmethod
    def from_env(cls) -> "Config":
        explicit = os.environ.get("TUYA_DEVICES_FILE")
        if explicit:
            devices_file: Path | None = Path(explicit).expanduser()
        else:
            devices_file = next((p for p in _search_paths() if p.is_file()), None)

        return cls(
            devices_file=devices_file,
            read_only=_env_bool("TUYA_READ_ONLY", False),
            connect_timeout=_env_float("TUYA_CONNECT_TIMEOUT", 5.0),
            cache_ttl=_env_float("TUYA_CACHE_TTL", 10.0),
            discovery_timeout=_env_float("TUYA_DISCOVERY_TIMEOUT", 12.0),
        )
