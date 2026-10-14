"""POST /v1/dasha: any level of any supported dasha system."""

from __future__ import annotations

from jyotisha import dashas as D
from jyotisha import jaimini as J
from jyotisha.ephemeris import SIGNS

from .chart_service import at_jd, cast, vimshottari_chain, vimshottari_children
from .errors import invalid
from .fmt import provenance
from .ids import ENGINE_GRAHA, GRAHA_ID, SIGN_IDS
from .models import DashaRequest
from .timeutil import iso


def _lord(name: str) -> dict:
    """Engine period names -> contract fields.

    Vimshottari/Ashtottari lords are grahas, Yogini periods are
    "Mangala (Moon)", rashi dashas are sign names."""
    if name in GRAHA_ID:
        return {"lord": GRAHA_ID[name]}
    if name in SIGNS:
        return {"lord": SIGN_IDS[SIGNS.index(name)]}
    yogini, _, planet = name.partition(" (")
    return {"lord": yogini.lower(), "planet": GRAHA_ID[planet.rstrip(")")]}


def _row(p: D.Period, zone: str) -> dict:
    return {**_lord(p.lord), "start": iso(p.start, zone), "end": iso(p.end, zone)}


def _matches(p: D.Period, wanted: str) -> bool:
    return _lord(p.lord)["lord"] == wanted


def build(req: DashaRequest) -> dict:
    chart, birth = cast(req.chart)
    zone = birth.display
    when = at_jd(req.at, zone)
    system = req.system
    applicable = None

    if system in ("chara", "narayana") and req.chart.timeUnknown:
        raise invalid("rashi dashas count from the lagna and need a birth time", "system")

    if system == "vimshottari":
        tree = D.vimshottari(chart, depth=1)
        chain = vimshottari_chain(tree, when)
        children = vimshottari_children
    elif system == "yogini":
        tree = D.yogini(chart, depth=3)
        chain = D.active(tree, when)
        children = None
    elif system == "ashtottari":
        tree = D.ashtottari(chart, depth=3)
        chain = D.active(tree, when)
        children = None
        applicable = D.ashtottari_applies(chart)
    elif system == "chara":
        tree = J.chara_dasha(chart, depth=2)
        chain = D.active(tree, when)
        children = None
    else:
        tree = J.narayana_dasha(chart, depth=2)
        chain = D.active(tree, when)
        children = None

    level = tree
    for depth, wanted in enumerate(req.path, start=1):
        found = next((p for p in level if _matches(p, wanted.lower())), None)
        if found is None:
            raise invalid(f"no period {wanted!r} at level {depth}", "path")
        if found.children:
            level = found.children
        elif children is not None and depth < 5:
            level = children(found)
        else:
            raise invalid(f"{system} has no level {depth + 1}", "path")

    if req.path and req.path[0] not in ENGINE_GRAHA and system in ("vimshottari", "ashtottari"):
        raise invalid("path entries are graha ids", "path")
    return {
        "system": system,
        "applicable": applicable,
        "path": [p.lower() for p in req.path],
        "periods": [_row(p, zone) for p in level],
        "at": iso(when, zone),
        "current": [{"level": p.level, **_row(p, zone)} for p in chain],
        "engine": provenance(req.chart.ayanamsa, req.chart.node),
    }
