"""Prashna: judging a chart cast for the moment a question is asked.

Prashna is the one branch that does not need a birth time, which makes it the
only part of this package usable on a nativity whose ascendant is unverified.
It is also the branch most exposed to the experimenter: the querent chooses
the moment. Treat the output as a reading, and log it in the sealed ledger
before the answer is known if you want it to mean anything.

Judgement follows the Tajika method used in Prashna Marga and the Kerala
tradition: the lagna lord signifies the querent, the lord of the house asked
about signifies the matter, and an *applying* aspect between them (ithasala)
says the matter completes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import panchanga as P
from . import upagraha as U
from .chart import SIGN_LORDS, Chart
from .ephemeris import SEVEN, SIGNS
from .tajika import DEEPTAMSHA, nakta_yamaya, tajika_aspects

# Which house answers which kind of question.
QUERY_HOUSE = {
    "self": 1,
    "health": 1,
    "wealth": 2,
    "family": 2,
    "siblings": 3,
    "courage": 3,
    "home": 4,
    "property": 4,
    "mother": 4,
    "education": 4,
    "children": 5,
    "romance": 5,
    "speculation": 5,
    "creativity": 5,
    "enemies": 6,
    "illness": 6,
    "debt": 6,
    "litigation": 6,
    "service": 6,
    "marriage": 7,
    "partnership": 7,
    "spouse": 7,
    "travel": 7,
    "obstacles": 8,
    "inheritance": 8,
    "longevity": 8,
    "fortune": 9,
    "higher education": 9,
    "guru": 9,
    "long journey": 9,
    "career": 10,
    "job": 10,
    "authority": 10,
    "reputation": 10,
    "gains": 11,
    "income": 11,
    "friends": 11,
    "desires": 11,
    "loss": 12,
    "expenditure": 12,
    "foreign residence": 12,
}


@dataclass
class Judgement:
    question: str
    house: int
    querent: str
    quesited: str
    verdict: str
    confidence: str
    reasons: list[str] = field(default_factory=list)
    timing: str = ""

    def __str__(self) -> str:
        lines = [
            f"  question   {self.question}",
            f"  house      {self.house}",
            f"  querent    lagna lord {self.querent}",
            f"  quesited   {self.house}th lord {self.quesited}",
            f"  verdict    {self.verdict}  ({self.confidence})",
        ]
        for r in self.reasons:
            lines.append(f"     - {r}")
        if self.timing:
            lines.append(f"  timing     {self.timing}")
        return "\n".join(lines)


def _applying(chart: Chart, a: str, b: str) -> tuple[bool, float, float]:
    """Is relative motion approaching the nearest exact Tajika angle?"""
    la, lb = chart.grahas[a].longitude, chart.grahas[b].longitude
    sep = abs((la - lb + 180) % 360 - 180)
    orb = (DEEPTAMSHA[a] + DEEPTAMSHA[b]) / 2.0
    best = min((abs(sep - ang), ang) for ang in (0, 60, 90, 120, 180))
    diff, angle = best
    if diff > orb:
        return False, sep, angle
    probe_days = 1e-3
    future_delta = (
        la + chart.grahas[a].speed * probe_days - lb - chart.grahas[b].speed * probe_days + 180
    ) % 360 - 180
    future_error = abs(abs(future_delta) - angle)
    applying = future_error + 1e-10 < diff
    return applying, sep, angle


def moon_void_of_course(chart: Chart) -> bool:
    """Does the Moon complete any Tajika aspect before it leaves the sign?"""
    moon = chart.grahas["Moon"]
    remaining = 30.0 - moon.degree
    for g in SEVEN:
        if g == "Moon":
            continue
        applying, sep, angle = _applying(chart, "Moon", g)
        if applying:
            gap = abs(sep - angle)
            if gap <= remaining:
                return False
    return True


def judge(chart: Chart, question: str, topic: str | None = None) -> Judgement:
    topic = (topic or "").lower().strip()
    house = QUERY_HOUSE.get(topic)
    if house is None:
        for key, h in QUERY_HOUSE.items():
            if key in question.lower():
                house, topic = h, key
                break
    house = house or 1

    querent = SIGN_LORDS[chart.asc.sign]
    quesited = SIGN_LORDS[chart.house_sign(house)]
    reasons, verdict, confidence = [], "unclear", "low"

    if querent == quesited:
        reasons.append(
            f"{querent} rules both the lagna and the "
            f"{house}th -- querent and matter are one significator"
        )
        verdict, confidence = "favourable", "moderate"
    else:
        applying, sep, angle = _applying(chart, querent, quesited)
        exact = abs(sep - angle)
        orb = (DEEPTAMSHA[querent] + DEEPTAMSHA[quesited]) / 2.0
        if exact <= orb and applying:
            verdict, confidence = "yes", "moderate"
            reasons.append(
                f"Ithasala: {querent} applying to {quesited} at "
                f"{angle} degrees ({exact:.1f} from exact, "
                f"orb {orb:.1f})"
            )
        elif exact <= orb:
            verdict, confidence = "no -- the moment has passed", "moderate"
            reasons.append(f"Ishrafa: {querent} separating from {quesited} at {angle} degrees")
        else:
            nk = [n for n in nakta_yamaya(chart) if set(n["between"]) == {querent, quesited}]
            if nk:
                verdict, confidence = "yes, through an intermediary", "low"
                for n in nk:
                    reasons.append(f"{n['kind']} via {n['via']}")
            else:
                verdict, confidence = "no", "moderate"
                reasons.append(f"no Tajika aspect between {querent} and {quesited} within orb")

    # Moon as co-significator
    if moon_void_of_course(chart):
        reasons.append("the Moon is void of course -- nothing is carried to completion")
        if verdict.startswith("yes"):
            verdict, confidence = "yes but it does not conclude", "low"
    else:
        for target in (querent, quesited):
            if target == "Moon":
                continue
            applying, sep, angle = _applying(chart, "Moon", target)
            if applying and abs(sep - angle) <= (DEEPTAMSHA["Moon"] + DEEPTAMSHA[target]) / 2.0:
                reasons.append(f"Kambool: the Moon applies to {target}")

    # afflictions
    up = U.kalavela_longitudes(chart)
    if "Gulika" in up:
        g_house = (up["Gulika"].sign - chart.asc.sign) % 12 + 1
        if g_house in (1, house):
            reasons.append(f"Gulika falls in house {g_house} -- obstruction to the matter")
            confidence = "low"
    if chart.combust(quesited):
        reasons.append(f"{quesited} is combust -- the matter is obscured")

    # timing: degrees to exact, read as units of time
    timing = ""
    if verdict.startswith("yes"):
        applying, sep, angle = _applying(chart, querent, quesited)
        gap = abs(sep - angle)
        movable = chart.asc.sign % 3
        unit = {0: "days", 1: "months", 2: "weeks"}[movable]
        timing = (
            f"about {gap:.1f} {unit} "
            f"({'movable' if movable == 0 else 'fixed' if movable == 1 else 'dual'} "
            f"lagna sets the unit)"
        )

    return Judgement(question, house, querent, quesited, verdict, confidence, reasons, timing)


def arudha_from_number(number: int, chart: Chart) -> dict:
    """The classical number-prashna: a number 1-108 fixes an arudha lagna."""
    n = ((number - 1) % 108) + 1
    sign = (n - 1) % 12
    navamsa = ((n - 1) // 12) % 9 + 1
    return {
        "number": n,
        "arudha_sign": SIGNS[sign],
        "arudha_house": (sign - chart.asc.sign) % 12 + 1,
        "navamsa": navamsa,
    }


def report(
    chart: Chart, question: str, topic: str | None = None, number: int | None = None, tz=0.0
) -> str:
    from .ephemeris import fmt

    pc = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)
    j = judge(chart, question, topic)
    lines = [
        f"=== PRASHNA — cast for {fmt(chart.jd, tz, True)} ===",
        "",
        chart.table(),
        "",
        f"  {pc.vara}, {pc.tithi_name} ({pc.paksha}), {pc.nakshatra_name}, hora of {pc.hora_lord}",
        "",
        str(j),
    ]
    if number is not None:
        a = arudha_from_number(number, chart)
        lines.append("")
        lines.append(
            f"  number {a['number']} -> arudha {a['arudha_sign']} "
            f"(house {a['arudha_house']}), navamsa {a['navamsa']}"
        )
    asp = [
        a
        for a in tajika_aspects(chart)
        if j.querent in (a["a"], a["b"]) or j.quesited in (a["a"], a["b"])
    ]
    if asp:
        lines.append("")
        lines.append("  aspects touching the significators:")
        for a in asp[:8]:
            lines.append(f"    {a['a']:8s}{a['aspect']:13s}{a['b']:9s} {a['kind']}")
    lines.append("")
    lines.append(
        "  Prashna is a reading, not a measurement. Seal it in the "
        "ledger before the outcome is known."
    )
    return "\n".join(lines)
