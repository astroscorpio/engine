"""Compact deterministic provenance for sealed calculations."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .ephemeris import backend_info
from .subjects import Subject


def _digest_bytes(chunks) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def code_hash() -> str:
    root = Path(__file__).resolve().parent
    files = sorted(root.glob("*.py"))
    return _digest_bytes(
        item for path in files for item in (path.name.encode(), b"\0", path.read_bytes(), b"\0")
    )


def subject_hash(subject: Subject) -> str:
    payload = json.dumps(
        asdict(subject),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def dependency_versions() -> dict[str, str]:
    packages = ("numpy", "pyswisseph", "scipy")
    found = {}
    for package in packages:
        try:
            found[package] = version(package)
        except PackageNotFoundError:
            found[package] = "absent"
    return found


def manifest(
    subject: Subject,
    *,
    technique_ids: list[str],
    config: dict,
) -> dict:
    return {
        "code_sha256": code_hash(),
        "subject_sha256": subject_hash(subject),
        "technique_ids": technique_ids,
        "config": config,
        "python": platform.python_version(),
        "dependencies": dependency_versions(),
        "ephemeris": backend_info(),
    }
