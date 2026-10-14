"""Writable user-data paths, separate from immutable corpus resources."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
RESOURCE_DATA = (
    Path(os.environ.get("JYOTISHA_RESOURCE_DIR", PACKAGE_ROOT / "data")).expanduser().resolve()
)


def user_data_dir() -> Path:
    explicit = os.environ.get("JYOTISHA_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser().resolve()
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share"
    target = base / "jyotisha"
    # Preserve an existing checkout without silently moving private records.
    legacy = RESOURCE_DATA / "ledger.jsonl"
    if legacy.exists() and not (target / "ledger.jsonl").exists():
        return RESOURCE_DATA
    return target


def user_path(name: str) -> Path:
    return user_data_dir() / name


def ensure_private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass


def secure_file(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        pass
