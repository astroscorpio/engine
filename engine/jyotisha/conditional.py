"""Conditional dashas, and the rules that modify a graha's ordinary reading.

Two things this package was getting wrong.

First, Vimshottari was applied unconditionally.  Parashara gives it as the
*default*, with a family of conditional dashas that take precedence when a
specific structural condition holds in the chart.  Most charts trigger none;
some trigger several, and then the tradition ranks them.

Second, a transit was read the same way for everybody.  A graha that is
retrograde at birth does not respond to a transiting retrograde the way a
direct-born graha does -- the classical position is that the *natal* condition
sets the baseline and the transit is read as a departure from it.  That is a
genuinely different reading for every graha that is retrograde from birth.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import panchanga as P
from .chart import SIGN_LORDS, Chart
from .dashas import Period, _build
from .ephemeris import DASHA_YEAR, SEVEN
from .vargas import varga

# --- conditional dasha applicability ---------------------------------------

# Each cycle: (name, total years, [(lord, years), ...]) using the
# nakshatra-based start rule of its own system.
CHATURASHITI = (
    "Chaturashiti Sama",
    84,
    [
        ("Sun", 12),
        ("Moon", 12),
        ("Mars", 12),
        ("Mercury", 12),
        ("Jupiter", 12),
        ("Venus", 12),
        ("Saturn", 12),
    ],
)
DWISAPTATI = (
    "Dwisaptati Sama",
    72,
    [
        ("Sun", 9),
        ("Moon", 9),
        ("Mars", 9),
        ("Mercury", 9),
        ("Jupiter", 9),
        ("Venus", 9),
        ("Saturn", 9),
        ("Rahu", 9),
    ],
)
SHATTRIMSHA = (
    "Shattrimsha Sama",
    36,
    [
        ("Sun", 1),
        ("Moon", 2),
        ("Mars", 3),
        ("Mercury", 4),
        ("Jupiter", 5),
        ("Venus", 6),
        ("Saturn", 7),
        ("Rahu", 8),
    ],
)
SHASHTIHAYANI = (
    "Shashtihayani",
    60,
    [
        ("Sun", 5),
        ("Moon", 5),
        ("Mars", 5),
        ("Mercury", 5),
        ("Jupiter", 10),
        ("Venus", 10),
        ("Saturn", 10),
        ("Rahu", 10),
    ],
)
DWADASOTTARI = (
    "Dwadasottari",
    112,
    [
        ("Sun", 7),
        ("Moon", 9),
        ("Mars", 11),
        ("Mercury", 13),
        ("Jupiter", 15),
        ("Venus", 17),
        ("Saturn", 19),
        ("Rahu", 21),
    ],
)
PANCHOTTARI = (
    "Panchottari",
    105,
    [
        ("Sun", 12),
        ("Moon", 13),
        ("Mars", 14),
        ("Mercury", 15),
        ("Jupiter", 16),
        ("Venus", 17),
        ("Saturn", 18),
    ],
)
SHODASOTTARI = (
    "Shodasottari",
    116,
    [
        ("Sun", 11),
        ("Moon", 12),
        ("Mars", 13),
        ("Mercury", 14),
        ("Jupiter", 15),
        ("Venus", 16),
        ("Saturn", 17),
        ("Rahu", 18),
    ],
)


def applicable(chart: Chart) -> list[dict]:
    """Which conditional dashas this chart actually triggers.

    Population rarity is given because it is the honest way to read these:
    a condition met by one chart in twelve is not a rare distinction.
    """
    out = []
    lagna = chart.asc.sign
    lagna_lord = SIGN_LORDS[lagna]
    tenth_lord = SIGN_LORDS[(lagna + 9) % 12]
    seventh_lord = SIGN_LORDS[(lagna + 6) % 12]
    pc = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)

    if chart.house(tenth_lord) == 10:
        out.append(
            {
                "dasha": CHATURASHITI,
                "rarity": "8.3%",
                "reason": f"10th lord {tenth_lord} sits in the 10th house",
            }
        )
    if chart.house(lagna_lord) == 7 or chart.house(seventh_lord) == 1:
        out.append(
            {
                "dasha": DWISAPTATI,
                "rarity": "16.7%",
                "reason": "lagna lord in the 7th, or 7th lord in the lagna",
            }
        )
    day_sun = pc.is_day_birth and pc.hora_lord == "Sun"
    night_moon = (not pc.is_day_birth) and pc.hora_lord == "Moon"
    if day_sun or night_moon:
        out.append(
            {
                "dasha": SHATTRIMSHA,
                "rarity": "11.1%",
                "reason": "day birth in the Sun's hora, or night birth in the Moon's hora",
            }
        )
    if chart.house("Sun") == 1:
        out.append(
            {"dasha": SHASHTIHAYANI, "rarity": "8.3%", "reason": "the Sun occupies the lagna"}
        )
    nav_sign = int(varga(chart.asc.longitude, 9) // 30)
    if SIGN_LORDS[nav_sign] == "Venus":
        out.append(
            {
                "dasha": DWADASOTTARI,
                "rarity": "16.7%",
                "reason": "the lagna falls in a navamsa ruled by Venus",
            }
        )
    if lagna == 3 and int(varga(chart.asc.longitude, 12) // 30) == 3:
        out.append(
            {
                "dasha": PANCHOTTARI,
                "rarity": "0.7%",
                "reason": "Cancer lagna in both rashi and dwadasamsa",
            }
        )
    if SIGN_LORDS[nav_sign] == "Moon":
        out.append(
            {
                "dasha": SHODASOTTARI,
                "rarity": "8.3%",
                "reason": "the lagna falls in the Moon's navamsa",
            }
        )
    return out


def build_conditional(chart: Chart, spec: tuple, depth: int = 3) -> list[Period]:
    """Run a conditional cycle from the Moon's nakshatra."""
    name, total, cycle = spec
    n = len(cycle)
    nak = chart.grahas["Moon"].nakshatra
    start_i = nak % n
    seq = cycle[start_i:] + cycle[:start_i]
    span = 360 / 27
    consumed = (chart.grahas["Moon"].longitude % span) / span
    start = chart.jd - consumed * seq[0][1] * DASHA_YEAR
    return _build(start, seq, total, total * DASHA_YEAR, 1, depth)


# --- natal condition modifies transit reading -------------------------------


@dataclass
class TransitContext:
    graha: str
    natal_retrograde: bool
    transit_retrograde: bool
    natal_combust: bool
    transit_combust: bool
    natal_dignity: str
    reading: str
    intensity: float


def retrograde_context(
    chart: Chart, graha: str, transit_speed: float, transit_combust: bool = False
) -> TransitContext:
    """How a transit reads *for this chart*, given the natal condition.

    The classical position, and the one modern practitioners state most
    plainly: a graha retrograde at birth has already internalised the
    reversed condition, so a transiting retrograde is familiar territory
    rather than disruption -- and conversely its *direct* motion is the
    unfamiliar state.  The polarity flips.
    """
    natal_r = chart.grahas[graha].retrograde
    transit_r = transit_speed < 0
    natal_c = chart.combust(graha)
    dignity = chart.dignity(graha)

    if natal_r and transit_r:
        reading = (
            "natal retrograde meeting transit retrograde -- the "
            "familiar mode. Reads as inward consolidation and "
            "revisiting, not as obstruction. The disruption most "
            "charts feel here is muted."
        )
        intensity = 0.4
    elif natal_r and not transit_r:
        reading = (
            "natal retrograde under a direct transit -- the "
            "*unfamiliar* mode for this chart. Outward demand arrives "
            "when the native's habit is to internalise. This is the "
            "harder half of the cycle here, which inverts the "
            "ordinary rule."
        )
        intensity = 0.85
    elif transit_r:
        reading = (
            "direct at birth, retrograde in transit -- the standard "
            "reading: delay, review, reversal, matters returning "
            "for rework."
        )
        intensity = 0.8
    else:
        reading = "direct at birth and in transit -- ordinary forward motion."
        intensity = 0.3

    if natal_c and transit_combust:
        reading += (
            " Combust natally and now -- the graha's weakness is "
            "constitutional rather than passing."
        )
    elif transit_combust and not natal_c:
        reading += (
            " Combust only in transit -- a temporary eclipse of function this chart is not used to."
        )
        intensity += 0.15

    if natal_r and dignity in ("exalted", "own", "moolatrikona"):
        reading += (
            " Retrograde while dignified is the configuration the "
            "texts warn is deceptively strong: capable, but the "
            "results arrive out of sequence."
        )
    return TransitContext(
        graha, natal_r, transit_r, natal_c, transit_combust, dignity, reading, min(intensity, 1.0)
    )


def natal_retrogrades(chart: Chart) -> list[str]:
    return [g for g in SEVEN if g not in ("Sun", "Moon") and chart.grahas[g].retrograde]


def report(chart: Chart, tz=0.0) -> str:
    from .dashas import active

    lines = ["=== CONDITIONAL DASHAS ==="]
    apps = applicable(chart)
    if not apps:
        lines.append("  none triggered -- Vimshottari applies unmodified")
    for a in apps:
        name, total, _ = a["dasha"]
        lines.append(f"  {name:22s} ({total}y)  applies: {a['reason']}")
        lines.append(f"  {'':22s}  population rarity {a['rarity']}")
        tree = build_conditional(chart, a["dasha"])
        now = active(tree, chart.jd + 23 * DASHA_YEAR)
        lines.append(f"  {'':22s}  at age 23: {'-'.join(p.lord for p in now)}")
    lines.append("")
    lines.append("=== NATAL RETROGRADE BASELINE ===")
    nr = natal_retrogrades(chart)
    lines.append(f"  retrograde at birth: {', '.join(nr) or 'none'}")
    return "\n".join(lines)
