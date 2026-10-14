"""Kuja (Mangal) dosha: one rule shared by the chart page and matching.

Source (docs/sources/kuja-dosha.md): V. S. Khankhoje, Sulabh Jyotish Gyana
(1943), pp. 223-226. Mars in the 1st, 4th, 7th, 8th or 12th house from the
lagna is inauspicious for marriage. No public-domain classical verse with the
five- or six-house rule was found, so this is the rule the verdict follows.

What common practice adds (the 2nd house, counting from the Moon or Venus) is
reported under `conventions` as "common practice, source pending" and never
feeds the verdict. The only cancellation shown is the same author's partner
rule (p. 226); he also asks for Mars's strength by sign and degree to be
weighed first, which is not assessed here.
"""

from __future__ import annotations

from jyotisha.chart import Chart

RULE = "khankhoje_1943"
SOURCE = "Khankhoje, Sulabh Jyotish Gyana (1943), pp. 223-226"
KUJA_HOUSES = {1, 4, 7, 8, 12}  # SJG p. 223
COMMON_HOUSES = {1, 2, 4, 7, 8, 12}  # common practice, source pending
# SJG p. 226: the groom's Mars in these houses wants the bride's Mars or Saturn in them.
CANCEL_HOUSES = {1, 4, 12}


def _from(chart: Chart, body: str, ref_sign: int) -> int:
    return (chart.grahas[body].sign - ref_sign) % 12 + 1


def status(chart: Chart, time_known: bool) -> dict:
    """One person's kuja dosha under the sourced rule, plus the conventions."""
    lagna = _from(chart, "Mars", chart.asc.sign) if time_known else None
    moon = _from(chart, "Mars", chart.grahas["Moon"].sign)
    venus = _from(chart, "Mars", chart.grahas["Venus"].sign)
    return {
        "verdict": None if lagna is None else lagna in KUJA_HOUSES,
        "rule": RULE,
        "source": SOURCE,
        "marsHouse": {"lagna": lagna, "moon": moon, "venus": venus},
        "conventions": {
            "second_house": None if lagna is None else lagna == 2,
            "from_moon": moon in COMMON_HOUSES,
            "from_venus": venus in COMMON_HOUSES,
        },
    }


def cancellation(groom: Chart | None, bride: Chart | None) -> dict | None:
    """SJG p. 226. Null unless both lagnas are known and the groom's Mars is in 1, 4 or 12."""
    if groom is None or bride is None:
        return None
    if _from(groom, "Mars", groom.asc.sign) not in CANCEL_HOUSES:
        return None
    bride_mars = _from(bride, "Mars", bride.asc.sign)
    bride_saturn = _from(bride, "Saturn", bride.asc.sign)
    return {
        "applies": bride_mars in CANCEL_HOUSES or bride_saturn in CANCEL_HOUSES,
        "by": RULE,
    }
