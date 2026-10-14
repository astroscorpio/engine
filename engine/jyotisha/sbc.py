"""Sarvatobhadra chakra, the real one.

The version in ``rare.py`` was a fourteen-pair toy: it knew that Krittika
pierces Vishakha and nothing else.  The actual chakra is a 9x9 grid of 81
cells holding the 28 nakshatras, 12 rasis, 5 tithi groups, 7 vaaras, 16
vowels and 20 consonants, and a graha standing on a perimeter cell casts
vedha along *three* rays -- straight ahead, and the two diagonals -- until
each ray leaves the grid.

That matters for us because of resolution.  Nearly everything else in this
package resolves to a season; a dasha level lasts months and a slow transit
sits on a degree for weeks.  The chakra moves with the Moon, so it repoints
every day, and at the 112-pada layer roughly every six hours.  It is the
only classical technique in the package that makes a claim narrow enough
for a day-dated event to actually test.

Grid, geometry and the 112-pada boundaries are all reproduced from first
principles and then checked against an independent reference implementation
(see ``validate()``); nothing here is hand-copied from a table.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from functools import lru_cache

from .chart import Chart
from .ephemeris import SEVEN, Position, positions

# --- the grid ---------------------------------------------------------------

# Row-major, nine rows of nine, north at the top and east to the right.  Cell
# numbers run 1..81 as (row - 1) * 9 + col.  Nakshatras occupy the perimeter
# with vowels at the four corners; rasis, tithi groups, vaaras and consonants
# fill the interior.
_A, _AA, _I, _II = "अ", "आ", "इ", "ई"

GRID: list[list[str]] = [
    [_A, "Krittika", "Rohini", "Mrigashira", "Ardra", "Punarvasu", "Pushya", "Ashlesha", _AA],
    ["Bharani", "उ", "अ*", "व", "क", "ह", "ड", "ऊ", "Magha"],
    ["Ashwini", "ल", "ऌ", "Ta", "Ge", "Cn", "ॡ", "म", "P.Phalguni"],
    ["Revati", "च", "Ar", "ओ", "Nanda", "औ", "Le", "ट", "U.Phalguni"],
    ["U.Bhadrapada", "द", "Pi", "Rikta", "Purna", "Bhadra", "Vi", "प", "Hasta"],
    ["P.Bhadrapada", "स", "Aq", "अः", "Jaya", "अं", "Li", "र", "Chitra"],
    ["Shatabhisha", "ग", "ऐ", "Cp", "Sg", "Sc", "ए", "त", "Swati"],
    ["Dhanishta", "ॠ", "ख", "ज", "भ", "य", "न", "ऋ", "Vishakha"],
    [_II, "Shravana", "Abhijit", "U.Ashadha", "P.Ashadha", "Mula", "Jyeshtha", "Anuradha", _I],
]

# The five tithi-group cells double as the weekday cells.  Keyed by the vara
# lord, which is what the rest of the package carries instead of a weekday.
VARA_CELL = {
    "Sun": "Nanda",
    "Mars": "Nanda",
    "Venus": "Rikta",
    "Saturn": "Purna",
    "Moon": "Bhadra",
    "Mercury": "Bhadra",
    "Jupiter": "Jaya",
}

# Tithi 1..30 to its five-fold class, the same cells as above.
TITHI_CLASS = ("Nanda", "Bhadra", "Jaya", "Rikta", "Purna")


def tithi_group(tithi: int) -> str:
    return TITHI_CLASS[(tithi - 1) % 5]


RASIS = ("Ar", "Ta", "Ge", "Cn", "Le", "Vi", "Li", "Sc", "Sg", "Cp", "Aq", "Pi")

# 28 nakshatras in zodiacal order, Abhijit between U.Ashadha and Shravana.
NAK28 = (
    "Ashwini",
    "Bharani",
    "Krittika",
    "Rohini",
    "Mrigashira",
    "Ardra",
    "Punarvasu",
    "Pushya",
    "Ashlesha",
    "Magha",
    "P.Phalguni",
    "U.Phalguni",
    "Hasta",
    "Chitra",
    "Swati",
    "Vishakha",
    "Anuradha",
    "Jyeshtha",
    "Mula",
    "P.Ashadha",
    "U.Ashadha",
    "Abhijit",
    "Shravana",
    "Dhanishta",
    "Shatabhisha",
    "P.Bhadrapada",
    "U.Bhadrapada",
    "Revati",
)

BENEFICS = frozenset({"Moon", "Mercury", "Jupiter", "Venus"})
MALEFICS = frozenset({"Sun", "Mars", "Saturn", "Rahu", "Ketu"})


def cell_num(row: int, col: int) -> int:
    return (row - 1) * 9 + col


def rowcol(cell: int) -> tuple[int, int]:
    return (cell - 1) // 9 + 1, (cell - 1) % 9 + 1


CONTENT: dict[int, str] = {cell_num(r + 1, c + 1): GRID[r][c] for r in range(9) for c in range(9)}
CELL_OF: dict[str, int] = {}
for _n, _v in CONTENT.items():
    CELL_OF.setdefault(_v, _n)

PERIMETER = [n for n in range(1, 82) if rowcol(n)[0] in (1, 9) or rowcol(n)[1] in (1, 9)]


# --- vedha geometry ---------------------------------------------------------


def _facing(row: int, col: int) -> tuple[int, int] | None:
    """Inward direction for an edge cell; None for corners and interior."""
    if (row in (1, 9)) and (col in (1, 9)):
        return None
    if row == 1:
        return (1, 0)
    if row == 9:
        return (-1, 0)
    if col == 1:
        return (0, 1)
    if col == 9:
        return (0, -1)
    return None


def _walk(row: int, col: int, dr: int, dc: int) -> list[int]:
    out = []
    r, c = row + dr, col + dc
    while 1 <= r <= 9 and 1 <= c <= 9:
        out.append(cell_num(r, c))
        r, c = r + dr, c + dc
    return out


@lru_cache(maxsize=1)
def rays() -> dict[int, dict[str, list[int]]]:
    """For every perimeter cell, the three vedha rays.

    A graha standing on the cell faces the centre.  ``front`` runs straight
    ahead; ``right`` and ``left`` are the diagonals to either hand.  Rotating
    the facing clockwise on screen (rows increase downward) sends (dr, dc) to
    (dc, -dr), which is the right hand.
    """
    out: dict[int, dict[str, list[int]]] = {}
    for n in PERIMETER:
        r, c = rowcol(n)
        face = _facing(r, c)
        if face is None:  # a corner: the diagonal only
            dr = 1 if r == 1 else -1
            dc = 1 if c == 1 else -1
            out[n] = {"right": _walk(r, c, dr, dc), "front": [], "left": []}
            continue
        dr, dc = face
        rdr, rdc = dc, -dr  # right hand
        out[n] = {
            "front": _walk(r, c, dr, dc),
            "right": _walk(r, c, dr + rdr, dc + rdc),
            "left": _walk(r, c, dr - rdr, dc - rdc),
        }
    return out


# --- the 112 sukshmamsha padas ---------------------------------------------

# Abhijit is not a 28th equal share.  It is carved out of the last quarter of
# U.Ashadha plus the first fifteenth of Shravana, which leaves three
# nakshatras of unequal length and every pada after them off the 3d20' grid.
# Getting this wrong shifts everything from Abhijit to Bharani -- a quarter of
# the wheel -- so the boundaries are built, not tabulated.
_NAK_SPAN = 360.0 / 27.0  # 13d20'
# U.Ashadha is the 21st nakshatra, so it opens at index 20; Abhijit takes its
# last quarter and the first fifteenth of Shravana.
_ABHIJIT_START = 20 * _NAK_SPAN + 3 * (_NAK_SPAN / 4)  # 276d40'
_ABHIJIT_END = 21 * _NAK_SPAN + _NAK_SPAN / 15  # 280d53'20"


@lru_cache(maxsize=1)
def nak28_bounds() -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    idx = 0
    for name in NAK28:
        if name == "Abhijit":
            out[name] = (_ABHIJIT_START, _ABHIJIT_END)
            continue
        start = idx * _NAK_SPAN
        end = start + _NAK_SPAN
        if name == "U.Ashadha":
            end = _ABHIJIT_START
        elif name == "Shravana":
            start = _ABHIJIT_END
        out[name] = (start, end)
        idx += 1
    return out


@lru_cache(maxsize=1)
def padas() -> list[dict]:
    """The 112 padas, numbered from Krittika-1 = 1 as the chakra counts them."""
    bounds = nak28_bounds()
    order = NAK28[NAK28.index("Krittika") :] + NAK28[: NAK28.index("Krittika")]
    out = []
    for nak in order:
        lo, hi = bounds[nak]
        step = (hi - lo) / 4.0
        for p in range(4):
            out.append(
                {
                    "index": len(out) + 1,
                    "nak": nak,
                    "pada": p + 1,
                    "start": (lo + p * step) % 360.0,
                    "span": step,
                }
            )
    return out


@lru_cache(maxsize=1)
def _pada_lookup() -> tuple[list[float], list[int]]:
    entries = sorted((p["start"] % 360.0, p["index"]) for p in padas())
    return [entry[0] for entry in entries], [entry[1] for entry in entries]


def pada112(longitude: float) -> int:
    """Which of the 112 padas a longitude falls in."""
    starts, indices = _pada_lookup()
    offset = bisect.bisect_right(starts, longitude % 360.0) - 1
    return indices[offset]


def nak28_of(longitude: float) -> str:
    return padas()[pada112(longitude) - 1]["nak"]


@lru_cache(maxsize=1)
def peripheral_vedha() -> dict[int, dict[str, int]]:
    """Pada-to-pada vedha: the terminal cell of each ray, pada reversed.

    A graha in the first pada of a nakshatra strikes the *fourth* pada of the
    nakshatra its ray lands on, and so on inward -- the two padas face each
    other across the chakra.
    """
    ray = rays()
    first: dict[str, int] = {}
    for p in padas():
        first.setdefault(p["nak"], p["index"])
    out: dict[int, dict[str, int]] = {}
    for p in padas():
        cell = CELL_OF[p["nak"]]
        targets = {}
        for arm in ("front", "right", "left"):
            path = ray[cell][arm]
            end = next((c for c in reversed(path) if CONTENT[c] in first), None)
            if end is None:
                continue
            targets[arm] = first[CONTENT[end]] + (4 - p["pada"])
        out[p["index"]] = targets
    return out


# --- reading the chakra for a chart ----------------------------------------


@dataclass
class Vedha:
    graha: str
    arm: str  # front | right | left
    cell: int
    target: str  # what got struck
    kind: str  # nakshatra | rasi | tithi | vara | letter
    benefic: bool


def natal_cells(chart: Chart, tithi_group: str = "", vara: str = "") -> dict[int, str]:
    """The cells a native is sensitive on: janma nakshatra and rasi, the
    lagna rasi, and every natal graha's nakshatra and rasi."""
    out: dict[int, str] = {}

    def mark(key: str, label: str) -> None:
        c = CELL_OF.get(key)
        if c:
            out.setdefault(c, label)

    moon = chart.grahas["Moon"]
    mark(nak28_of(moon.longitude), "janma nakshatra")
    mark(RASIS[moon.sign], "janma rasi")
    mark(RASIS[chart.asc.sign], "lagna rasi")
    if tithi_group:
        mark(tithi_group, "janma tithi")
    if vara:
        mark(VARA_CELL.get(vara, ""), "janma vara")
    for name in SEVEN + ["Rahu", "Ketu"]:
        g = chart.grahas.get(name)
        if g is None:
            continue
        mark(nak28_of(g.longitude), f"natal {name} nakshatra")
        mark(RASIS[g.sign], f"natal {name} rasi")
    return out


def strikes(
    chart: Chart,
    jd: float,
    targets: dict[int, str] | None = None,
    tithi_group: str = "",
    vara: str = "",
    *,
    moving: dict[str, Position] | None = None,
) -> list[Vedha]:
    """Every vedha the transiting grahas are casting on the native today."""
    if targets is None:
        targets = natal_cells(chart, tithi_group, vara)
    moving = moving or positions(jd, chart.ayanamsa, chart.node)
    ray = rays()
    out: list[Vedha] = []
    for name in SEVEN + ["Rahu", "Ketu"]:
        cell = CELL_OF.get(nak28_of(moving[name].longitude))
        if cell is None or cell not in ray:
            continue
        for arm, path in ray[cell].items():
            for c in path:
                if c in targets:
                    kind = (
                        "nakshatra"
                        if CONTENT[c] in NAK28
                        else "rasi"
                        if CONTENT[c] in RASIS
                        else "tithi"
                        if CONTENT[c] in ("Nanda", "Bhadra", "Jaya", "Rikta", "Purna")
                        else "letter"
                    )
                    out.append(Vedha(name, arm, c, targets[c], kind, name in BENEFICS))
    return out


def score(
    chart: Chart,
    jd: float,
    targets: dict[int, str] | None = None,
    tithi_group: str = "",
    vara: str = "",
    *,
    moving: dict[str, Position] | None = None,
) -> float:
    """Benefic vedha minus malefic vedha, in units of one strike.

    The texts grade malefic vedha sharply -- one is friction, two costs
    money, three is defeat, four is death -- but that ladder is counted on a
    *single* element, not summed across the whole nativity.  Escalating on
    the total instead would make the score scale with how many natal cells
    happen to be listed, which is an artefact of bookkeeping rather than of
    the sky.
    """
    per_cell: dict[int, list[bool]] = {}
    for h in strikes(
        chart,
        jd,
        targets,
        tithi_group,
        vara,
        moving=moving,
    ):
        per_cell.setdefault(h.cell, []).append(h.benefic)
    total = 0.0
    for flags in per_cell.values():
        good = sum(1 for b in flags if b)
        bad = len(flags) - good
        total += good - bad * (1.0 + 0.25 * max(0, bad - 1))
    return total


# --- validation -------------------------------------------------------------


def validate(spec: dict) -> list[str]:
    """Check the derived grid and pada map against an external reference.

    ``spec`` is the reference workbook's own tables.  Every ray and every one
    of the 112 pada triples has to agree; anything that does not is returned
    rather than raised, so a disagreement can be inspected instead of
    silently swallowed.
    """
    problems: list[str] = []
    ray = rays()
    for num, want in spec["cellmap"].items():
        num = int(num)
        got = ray.get(num)
        if got is None:
            problems.append(f"cell {num}: not on the perimeter")
            continue
        for arm in ("front", "right", "left"):
            if list(want[arm]) != got[arm]:
                problems.append(
                    f"cell {num} ({want['content']}) {arm}: "
                    f"reference {want[arm]} != derived {got[arm]}"
                )
    per = peripheral_vedha()
    for num, want in spec["pada112"].items():
        num = int(num)
        got = per.get(num, {})
        for arm in ("front", "right", "left"):
            if want.get(arm) and want[arm] != got.get(arm):
                problems.append(
                    f"pada {num} ({want['nak']}-{want['pada']}) {arm}: "
                    f"reference {want[arm]} != derived {got.get(arm)}"
                )
        lo = padas()[num - 1]["start"]
        drift = (lo - want["start"] + 180.0) % 360.0 - 180.0
        if abs(drift) > 1e-6:
            problems.append(f"pada {num}: start {lo} != {want['start']}")
    return problems
