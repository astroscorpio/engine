"""Fail-fast installation and numerical verification."""

from __future__ import annotations

import json

from jyotisha import sbc
from jyotisha.ashtakavarga import bhinna
from jyotisha.data_manifest import verify_manifest
from jyotisha.ephemeris import backend_info
from jyotisha.storage import RESOURCE_DATA
from jyotisha.subjects import EXAMPLE

EXPECTED_ASCENDANT = 45.204993017
EXPECTED_GRAHAS = {
    "Sun": 275.467092115,
    "Moon": 218.701853256,
    "Mars": 201.647511149,
    "Mercury": 290.612653624,
    "Jupiter": 37.382392892,
    "Venus": 322.545625115,
    "Saturn": 30.222373107,
    "Rahu": 81.631042279,
    "Ketu": 261.631042279,
}
EXPECTED_BAV_TOTALS = {
    "Sun": 48,
    "Moon": 49,
    "Mars": 39,
    "Mercury": 54,
    "Jupiter": 56,
    "Venus": 52,
    "Saturn": 39,
}


def main() -> None:
    chart = EXAMPLE.chart()
    errors = []
    if backend_info()["actual"] != "swiss-files":
        errors.append("Swiss Ephemeris data files not found: set SE_EPHE_PATH")
    if abs(chart.asc.longitude - EXPECTED_ASCENDANT) > 1e-8:
        errors.append("ascendant golden value changed")
    for name, expected in EXPECTED_GRAHAS.items():
        if abs(chart.grahas[name].longitude - expected) > 1e-8:
            errors.append(f"{name} golden longitude changed")
    totals = {name: sum(values) for name, values in bhinna(chart).items()}
    if totals != EXPECTED_BAV_TOTALS:
        errors.append("canonical BAV totals changed")
    spec_path = RESOURCE_DATA / "sbc_spec.json"
    sbc_errors: list[str] | None = None
    if spec_path.exists():
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        sbc_errors = sbc.validate(spec)
        errors.extend(f"SBC: {problem}" for problem in sbc_errors)
    manifest_errors = verify_manifest()
    errors.extend(f"data: {problem}" for problem in manifest_errors)
    report = {
        "status": "pass" if not errors else "fail",
        "backend": backend_info(),
        "natal_golden": not any("golden" in error for error in errors),
        "bav_canonical": totals == EXPECTED_BAV_TOTALS,
        "sbc_reference_errors": sbc_errors,
        "data_manifest_errors": manifest_errors,
        "errors": errors,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
