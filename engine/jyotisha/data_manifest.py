"""Data-snapshot checksum validation."""

from __future__ import annotations

import hashlib
import json

from .storage import RESOURCE_DATA


def verify_manifest() -> list[str]:
    path = RESOURCE_DATA / "manifest.json"
    if not path.exists():
        if not RESOURCE_DATA.exists():
            return []
        return ["data/manifest.json is missing"]
    spec = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    for name, metadata in spec.get("files", {}).items():
        target = RESOURCE_DATA / name
        if not target.exists():
            errors.append(f"{name}: missing")
            continue
        digest = hashlib.sha256()
        with target.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        expected = metadata.get("sha256")
        if expected and actual != expected:
            errors.append(f"{name}: checksum mismatch")
    return errors


def manifest_warnings() -> list[str]:
    """Report provenance gaps without pretending they are checksum failures."""
    path = RESOURCE_DATA / "manifest.json"
    if not path.exists():
        return ["external research-data manifest is unavailable"]
    spec = json.loads(path.read_text(encoding="utf-8"))
    warnings = []
    for name, metadata in spec.get("files", {}).items():
        if metadata.get("provenance_status") == "incomplete":
            warnings.append(f"{name}: source provenance is incomplete")
        if not metadata.get("source") and not metadata.get("derived_from"):
            warnings.append(f"{name}: source or derivation is not documented")
    return warnings
