"""Framework-free router shared by the Lambda handler and the dev server.

Only the site's API gateway calls this service, so it stays lean: no web framework
on the cold-start path, pydantic for input validation, plain dicts out.
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import time
from collections.abc import Callable
from urllib.parse import parse_qs

from pydantic import BaseModel, ValidationError

from . import (
    chart_service,
    dasha_service,
    festivals,
    griha_pravesh,
    matching,
    meta,
    muhurta_service,
    mundan,
    observances,
    panchang_service,
    pitru_paksha,
    purchase,
    transit_service,
    vivah,
)
from .errors import ApiError
from .models import (
    ChartRequest,
    DashaRequest,
    EkadashiQuery,
    EventsQuery,
    GocharaQuery,
    MatchingRequest,
    MonthQuery,
    MuhurtaCheck,
    MuhurtaRequest,
    PanchangQuery,
    TransitRequest,
)

log = logging.getLogger("astro_compute")

PATTERN_HINTS = {
    "time": "must be HH:MM or HH:MM:SS (24-hour)",
    "utcOffset": "must look like +05:30 or -04:00",
    "hours": "must look like 08:00-20:00",
}


def _parse[M: BaseModel](model: type[M], data: object) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = [str(p) for p in first.get("loc", ()) if p != "__root__"]
        if len(loc) > 1 and loc[0] in ("bride", "groom") and loc[1] in ("chart", "star", "name"):
            del loc[1]  # the union tag of a matching partner, not a real field
        field = ".".join(loc) or None
        message = first.get("msg", "invalid input").removeprefix("Value error, ")
        if first.get("type") == "string_pattern_mismatch":
            message = PATTERN_HINTS.get(str(first["loc"][-1]), "has the wrong format")
            message = f"{first['loc'][-1]} {message}"
        raise ApiError("invalid_input", message, 400, field) from exc


def _json_body(body: bytes | str | None) -> object:
    if not body:
        raise ApiError("invalid_input", "a JSON body is required", 400)
    try:
        return json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ApiError("invalid_input", "body is not valid JSON", 400) from exc


ROUTES: dict[tuple[str, str], Callable[[dict, bytes | str | None], dict]] = {
    ("GET", "/v1/health"): lambda q, b: {"ok": True, "engine": meta.engine_info()},
    ("GET", "/v1/meta"): lambda q, b: meta.dictionary(q.get("lang", "en")),
    ("POST", "/v1/chart"): lambda q, b: chart_service.build(_parse(ChartRequest, _json_body(b))),
    ("POST", "/v1/dasha"): lambda q, b: dasha_service.build(_parse(DashaRequest, _json_body(b))),
    ("GET", "/v1/panchang"): lambda q, b: panchang_service.build(_parse(PanchangQuery, q)),
    ("GET", "/v1/panchang/month"): lambda q, b: panchang_service.month(_parse(MonthQuery, q)),
    ("GET", "/v1/observances/ekadashi"): lambda q, b: observances.ekadashi(
        _parse(EkadashiQuery, q)
    ),
    ("GET", "/v1/observances/purnima"): lambda q, b: observances.purnima(_parse(EkadashiQuery, q)),
    ("GET", "/v1/observances/amavasya"): lambda q, b: observances.amavasya(
        _parse(EkadashiQuery, q)
    ),
    ("GET", "/v1/observances/pradosha"): lambda q, b: observances.pradosha(
        _parse(EkadashiQuery, q)
    ),
    ("GET", "/v1/observances/sankashti"): lambda q, b: observances.sankashti(
        _parse(EkadashiQuery, q)
    ),
    ("GET", "/v1/observances/pitru-paksha"): lambda q, b: pitru_paksha.pitru_paksha(
        _parse(EkadashiQuery, q)
    ),
    **{
        ("GET", f"/v1/festivals/{kind}"): (
            lambda k: lambda q, b: festivals.festival(k, _parse(EkadashiQuery, q))
        )(kind)
        for kind in festivals.FESTIVALS
    },
    ("GET", "/v1/transits"): lambda q, b: transit_service.build(_parse(TransitRequest, q)),
    ("GET", "/v1/gochara"): lambda q, b: transit_service.moon_sign(_parse(GocharaQuery, q)),
    ("GET", "/v1/muhurat/vivah"): lambda q, b: vivah.vivah(_parse(EkadashiQuery, q)),
    ("GET", "/v1/muhurat/griha-pravesh"): lambda q, b: griha_pravesh.griha_pravesh(
        _parse(EkadashiQuery, q)
    ),
    ("GET", "/v1/muhurat/mundan"): lambda q, b: mundan.mundan(_parse(EkadashiQuery, q)),
    ("GET", "/v1/muhurat/vehicle"): lambda q, b: purchase.vehicle(_parse(EkadashiQuery, q)),
    ("GET", "/v1/muhurat/property"): lambda q, b: purchase.property_(_parse(EkadashiQuery, q)),
    ("GET", "/v1/transits/events"): lambda q, b: transit_service.events(_parse(EventsQuery, q)),
    ("POST", "/v1/transits"): lambda q, b: transit_service.build(
        _parse(TransitRequest, _json_body(b))
    ),
    ("POST", "/v1/matching"): lambda q, b: matching.build(_parse(MatchingRequest, _json_body(b))),
    ("GET", "/v1/muhurta"): lambda q, b: muhurta_service.find(_parse(MuhurtaRequest, q)),
    ("POST", "/v1/muhurta"): lambda q, b: muhurta_service.find(
        _parse(MuhurtaRequest, _json_body(b))
    ),
    ("GET", "/v1/muhurta/check"): lambda q, b: muhurta_service.check(_parse(MuhurtaCheck, q)),
    ("POST", "/v1/muhurta/check"): lambda q, b: muhurta_service.check(
        _parse(MuhurtaCheck, _json_body(b))
    ),
}


def _authorised(headers: dict[str, str]) -> bool:
    key = os.environ.get("COMPUTE_KEY")
    if not key:  # local dev server
        return True
    return hmac.compare_digest(headers.get("x-compute-key", ""), key)


def handle(
    method: str, path: str, query: dict[str, str], body: bytes | str | None, headers: dict[str, str]
) -> tuple[int, dict]:
    started = time.perf_counter()
    try:
        if not _authorised(headers):
            raise ApiError("unauthorized", "missing or wrong compute key", 401)
        route = ROUTES.get((method.upper(), path.rstrip("/") or "/"))
        if route is None:
            known = {p for _, p in ROUTES}
            if path in known:
                raise ApiError("invalid_input", f"{method} is not allowed on {path}", 405)
            raise ApiError("not_found", f"no route {path}", 404)
        return 200, route(query, body)
    except ApiError as exc:
        return exc.status, exc.body()
    except Exception:
        log.exception("unhandled error on %s %s", method, path)
        return 500, ApiError("internal", "computation failed", 500).body()
    finally:
        log.info("%s %s %.0f ms", method, path, (time.perf_counter() - started) * 1000)


def query_dict(raw: str) -> dict[str, str]:
    return {k: v[-1] for k, v in parse_qs(raw, keep_blank_values=False).items()}


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
