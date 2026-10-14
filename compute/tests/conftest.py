import json
import os
from pathlib import Path

import pytest

# Production reads the Swiss Ephemeris data files; so do the tests (scripts/fetch_ephe.sh).
_EPHE = Path(__file__).resolve().parents[2] / "engine" / "ephe"
if not os.environ.get("SE_EPHE_PATH") and _EPHE.is_dir():
    os.environ["SE_EPHE_PATH"] = str(_EPHE)

from astro_compute import app  # noqa: E402  (after SE_EPHE_PATH: the engine reads it on import)

EXAMPLE = {
    "name": "Example",
    "date": "2001-01-19",
    "time": "14:05",
    "place": {"name": "New Delhi, India", "lat": 28.6139, "lon": 77.2090, "tz": "Asia/Kolkata"},
}
AT = "2026-10-14T12:00:00+05:30"
DELHI = {"lat": "28.6139", "lon": "77.2090", "tz": "Asia/Kolkata"}


def call(method, path, query=None, body=None, headers=None):
    raw = json.dumps(body) if body is not None else None
    return app.handle(method, path, query or {}, raw, headers or {})


@pytest.fixture(scope="session")
def chart():
    status, out = call(
        "POST",
        "/v1/chart",
        body={
            **EXAMPLE,
            "vargas": "all",
            "include": [
                "dasha",
                "yogas",
                "ashtakavarga",
                "strength",
                "states",
                "jaimini",
                "points",
            ],
            "at": AT,
        },
    )
    assert status == 200, out
    return out


@pytest.fixture(scope="session")
def panchang():
    status, out = call("GET", "/v1/panchang", {"date": "2026-10-14", **DELHI})
    assert status == 200, out
    return out


@pytest.fixture(scope="session")
def meta():
    status, out = call("GET", "/v1/meta", {"lang": "en"})
    assert status == 200
    return out
