"""Upagrahas (shadowy points) and the special lagnas.

Two families.  The kala-velas -- Gulika, Mandi, Kala, Mrityu and the rest --
are time divisions of the day or night, so they depend on sunrise.  Dhuma and
its chain are pure arithmetic on the Sun.  The special lagnas are alternative
rising points that advance at their own rates from sunrise.
"""

from __future__ import annotations

from . import panchanga as P
from .chart import SIGN_LORDS, Chart
from .ephemeris import Position, positions

# Which eighth of the day or night each graha rules, counting from the lord of
# the weekday.  The eighth part is lordless -- Gulika takes the Saturn part.
KALAVELA = {
    "Kala": "Sun",
    "Mrityu": "Mars",
    "Artha Prahara": "Mercury",
    "Yama Ghantaka": "Jupiter",
    "Kodanda": "Venus",
    "Gulika": "Saturn",
    "Mandi": "Saturn",
}


def kalavela_longitudes(chart: Chart) -> dict[str, Position]:
    """Rising degree at the start of each graha's eighth of day or night.

    Mandi and Gulika are both taken from Saturn's portion; the tradition
    splits on whether to use its beginning or its end, so both are given.
    """
    pc = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)
    if pc.is_day_birth:
        start, span = pc.sunrise, (pc.sunset - pc.sunrise) / 8.0
        first = P.VARA_LORDS.index(pc.vara)
    else:
        start, span = pc.sunset, (pc.next_sunrise - pc.sunset) / 8.0
        # the night sequence begins with the lord of the 5th weekday on
        first = (P.VARA_LORDS.index(pc.vara) + 4) % 7
    order = [P.VARA_LORDS[(first + i) % 7] for i in range(8)]

    from .ephemeris import ascendant

    out: dict[str, Position] = {}
    for name, ruler in KALAVELA.items():
        if ruler not in order:
            continue
        i = order.index(ruler)
        t = start + i * span
        if name == "Gulika":
            t = start + (i + 1) * span  # end of the portion
        asc, _ = ascendant(t, chart.lat, chart.lon, chart.ayanamsa)
        out[name] = Position(name, asc.longitude)
    return out


def dhuma_family(chart: Chart) -> dict[str, Position]:
    """Dhuma and its derived chain, all fixed offsets from the Sun."""
    sun = chart.grahas["Sun"].longitude
    dhuma = (sun + 133 + 20 / 60) % 360
    vyatipata = (360 - dhuma) % 360
    parivesha = (vyatipata + 180) % 360
    indrachapa = (360 - parivesha) % 360
    upaketu = (indrachapa + 16 + 40 / 60) % 360
    return {
        n: Position(n, v)
        for n, v in (
            ("Dhuma", dhuma),
            ("Vyatipata", vyatipata),
            ("Parivesha", parivesha),
            ("Indrachapa", indrachapa),
            ("Upaketu", upaketu),
        )
    }


def special_lagnas(chart: Chart) -> dict[str, Position]:
    """Bhava, Hora, Ghatika, Varnada, Sree and Indu lagnas.

    The first three advance from the Sun's place at sunrise at one sign per
    5, 2.5 and 1 ghatis respectively (a ghati is 24 minutes).
    """
    pc = P.compute(chart.jd, chart.lat, chart.lon, chart.ayanamsa)
    sun_at_rise = positions(pc.sunrise, chart.ayanamsa)["Sun"].longitude
    ghatis = (chart.jd - pc.sunrise) * 60.0  # 60 ghatis to a day

    bhava = (sun_at_rise + ghatis * (30.0 / 5.0)) % 360
    hora = (sun_at_rise + ghatis * (30.0 / 2.5)) % 360
    ghatika = (sun_at_rise + ghatis * 30.0) % 360

    # Varnada: count lagna from Aries and hora lagna from Pisces (or the
    # reverse for even lagnas), then add or subtract.
    lagna_sign, hora_sign = chart.asc.sign, int(hora // 30)
    if lagna_sign % 2 == 0:
        a = lagna_sign + 1
    else:
        a = 12 - lagna_sign
    if hora_sign % 2 == 0:
        b = hora_sign + 1
    else:
        b = 12 - hora_sign
    total = (a + b) if (lagna_sign % 2 == 0) == (hora_sign % 2 == 0) else abs(a - b)
    varnada = ((lagna_sign + total - 1) % 12) * 30 + chart.asc.degree

    # Sree lagna: lagna plus the fraction of its nakshatra the Moon has
    # traversed, applied as whole signs.
    moon = chart.grahas["Moon"]
    frac = (moon.longitude % (360 / 27)) / (360 / 27)
    sree = (chart.asc.longitude + frac * 360.0) % 360

    # Indu lagna: kala values of the 9th lords from lagna and from the Moon.
    kala = {"Sun": 30, "Moon": 16, "Mars": 6, "Mercury": 8, "Jupiter": 10, "Venus": 12, "Saturn": 1}
    ninth_from_lagna = SIGN_LORDS[(chart.asc.sign + 8) % 12]
    ninth_from_moon = SIGN_LORDS[(moon.sign + 8) % 12]
    total_kala = kala.get(ninth_from_lagna, 0) + kala.get(ninth_from_moon, 0)
    indu = ((moon.sign + (total_kala % 12 or 12) - 1) % 12) * 30

    return {
        n: Position(n, v)
        for n, v in (
            ("Bhava Lagna", bhava),
            ("Hora Lagna", hora),
            ("Ghatika Lagna", ghatika),
            ("Varnada Lagna", varnada),
            ("Sree Lagna", sree),
            ("Indu Lagna", indu),
        )
    }


def all_points(chart: Chart) -> dict[str, Position]:
    out = {}
    out.update(kalavela_longitudes(chart))
    out.update(dhuma_family(chart))
    out.update(special_lagnas(chart))
    return out


def report(chart: Chart) -> str:
    pts = all_points(chart)
    lines = [f"{'point':16s}{'position':16s}{'house':>6s}  lord of sign"]
    for name, p in pts.items():
        house = (p.sign - chart.asc.sign) % 12 + 1
        lines.append(f"{name:16s}{str(p):16s}{house:6d}  {SIGN_LORDS[p.sign]}")
    return "\n".join(lines)
