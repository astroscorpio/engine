"""Yoga rules against their texts, on hand-placed charts (whole signs; 0 = Aries)."""

from __future__ import annotations

from jyotisha import yogas as Y
from jyotisha.chart import Chart
from jyotisha.ephemeris import Position

AWAY = 8  # Sagittarius: somewhere out of the way


def make(lagna: int, **signs: int) -> Chart:
    """Each graha at 15 degrees of the given sign; the Moon 120 degrees from the Sun
    unless placed, so it is a waxing benefic and nothing is combust by accident."""
    base = {g: AWAY for g in ("Sun", "Mars", "Mercury", "Jupiter", "Venus", "Saturn")}
    base |= {"Moon": (signs.get("Sun", AWAY) + 4) % 12, "Rahu": 1, "Ketu": 7}
    base |= signs
    grahas = {g: Position(g, s * 30 + 15.0, 1.0) for g, s in base.items()}
    return Chart(
        jd=2451545.0, lat=0.0, lon=0.0, grahas=grahas, asc=Position("Ascendant", lagna * 30 + 1.0)
    )


class Strong:
    def strong(self, g: str) -> bool:
        return True


class Weak:
    def strong(self, g: str) -> bool:
        return False


def names(ys: list[Y.Yoga]) -> list[str]:
    return [y.name for y in ys]


def test_sunapha_anapha_durudhara_leave_out_the_sun():
    # PD 6.5 "planets other than the Sun"; only the Sun beside the Moon is Kemadruma.
    c = make(0, Moon=0, Sun=1, Mars=6, Mercury=6, Jupiter=6, Venus=6, Saturn=6)
    ys = Y.lunar_yogas(c)
    assert "Sunapha Yoga" not in names(ys) and "Kemadruma Yoga" in names(ys)
    kema = next(y for y in ys if y.name == "Kemadruma Yoga")
    # PD 6.5's minority cancellations, each reported as holding or not.
    assert kema.checks == (
        ("moon_in_kendra", True),
        ("planet_with_moon", False),
        ("planet_in_kendra_from_moon", True),
    )
    assert next(
        y for y in Y.lunar_yogas(c, lagna_known=False) if y.name == "Kemadruma Yoga"
    ).checks[0] == (
        "moon_in_kendra",
        None,
    )
    assert kema.source == "chandra" and not kema.reads_lagna
    c = make(0, Moon=0, Sun=1, Mars=1)
    assert "Sunapha Yoga" in names(Y.lunar_yogas(c))


def test_shakata_is_cancelled_by_the_moon_in_a_kendra_from_the_lagna():
    # PD 6.14: the Moon 6th from Jupiter, "But if the Moon be in a Kendra house
    # from the Lagna, there is no Sakata."
    assert "Shakata Yoga" in names(Y.lunar_yogas(make(0, Jupiter=0, Moon=5)))
    assert "Shakata Yoga" not in names(Y.lunar_yogas(make(2, Jupiter=0, Moon=5)))


def test_adhi_needs_all_three_benefics_in_the_6th_to_8th():
    c = make(9, Moon=0, Mercury=5, Jupiter=6, Venus=7)
    adhi = [y for y in Y.lunar_yogas(c) if y.name == "Adhi Yoga"]
    assert [(y.reckoned_from, y.source) for y in adhi] == [("moon", "adhi_moon")]
    c = make(9, Moon=0, Mercury=6, Jupiter=6, Venus=2)  # two of three: no Adhi
    assert "Adhi Yoga" not in names(Y.lunar_yogas(c))
    c = make(0, Moon=3, Mercury=5, Jupiter=6, Venus=7)  # from the lagna only (PD 6.42)
    adhi = [y for y in Y.lunar_yogas(c) if y.name == "Adhi Yoga"]
    assert [(y.reckoned_from, y.source) for y in adhi] == [("lagna", "adhi_lagna")]


def test_gaja_kesari_follows_phaladipika_and_flags_bphs():
    c = make(0, Moon=0, Jupiter=3, Venus=3, Sun=AWAY)  # exalted, joined by Venus
    gk = next(y for y in Y.lunar_yogas(c) if y.name == "Gaja Kesari Yoga")
    assert gk.variants == {"bphs": True}
    c = make(0, Moon=0, Jupiter=9)  # debilitated: PD's yoga stands, BPHS's does not
    gk = next(y for y in Y.lunar_yogas(c) if y.name == "Gaja Kesari Yoga")
    assert gk.variants == {"bphs": False}


def test_mahapurusha_own_or_exalted_from_lagna_and_from_the_moon():
    c = make(1, Mars=9, Moon=6)  # Mars exalted in the 9th from a Taurus lagna, 4th from the Moon
    ys = Y.mahapurusha(c, Strong())
    assert [(y.name, y.reckoned_from, y.source) for y in ys] == [
        ("Ruchaka Yoga", "moon", "mahapurusha_moon")
    ]
    c = make(0, Mars=9, Moon=0)  # 10th from both
    ys = Y.mahapurusha(c, Weak())
    assert [(y.reckoned_from, y.variants) for y in ys] == [("lagna", {"bphs": False}), ("moon", {})]
    c = make(0, Mars=4)  # Leo is a friend's sign, not own or exaltation
    assert Y.mahapurusha(c, Strong()) == []


def test_raja_yoga_links_and_the_v15_exclusion():
    # Aries lagna: the Moon (lord of the 4th) in Sagittarius, Jupiter's sign, and
    # Jupiter (lord of the 9th) aspecting it from Leo: BPHS's one-way link.
    c = make(0, Moon=8, Jupiter=4, Sun=AWAY)
    raja = [y for y in Y.raja_yogas(c) if set(y.grahas) == {"Moon", "Jupiter"}]
    assert raja and "aspected by Jupiter" in raja[0].detail
    # Cancer lagna: Venus rules the 4th and 11th, Jupiter the 9th and 6th. Both rule a
    # krura house (3, 6, 11), so their conjunction alone gives no yoga (v.15).
    c = make(3, Venus=9, Jupiter=9)
    assert not [y for y in Y.raja_yogas(c) if set(y.grahas) == {"Venus", "Jupiter"}]


def test_neecha_bhanga_mutual_kendras_7_27():
    # The Sun debilitated in Libra; Venus (its dispositor) and Mars (lord of Aries)
    # in kendras from each other, neither in a kendra from the lagna or the Moon.
    c = make(1, Sun=6, Moon=6, Mercury=6, Venus=2, Mars=5, Jupiter=8, Saturn=10)
    (nb,) = Y.neecha_bhanga(c)
    assert nb.detail.endswith("Venus and Mars in kendras from each other (7.27)")
    assert nb.grahas == ("Sun", "Venus", "Mars")


def test_amala_saraswati_lakshmi():
    c = make(0, Mercury=9, Moon=0)  # Mercury in the 10th from the lagna and the Moon
    amala = [y for y in Y.amala_saraswati_lakshmi(c, Weak()) if y.name == "Amala Yoga"]
    assert [y.reckoned_from for y in amala] == ["lagna", "moon"]
    c = make(0, Mercury=0, Jupiter=8, Venus=1)  # kendra, trikona, 2nd; Jupiter in own sign
    assert "Saraswati Yoga" in names(Y.amala_saraswati_lakshmi(c, Strong()))
    assert "Saraswati Yoga" not in names(Y.amala_saraswati_lakshmi(c, Weak()))
    # Aries lagna: Jupiter, lord of the 9th, exalted in the 4th; Mars strong.
    c = make(0, Jupiter=3, Venus=6)
    lak = next(y for y in Y.amala_saraswati_lakshmi(c, Strong()) if y.name == "Lakshmi Yoga")
    assert lak.source == "lakshmi" and lak.variants == {"phaladipika": True}
    c = make(0, Jupiter=3, Venus=2)
    lak = next(y for y in Y.amala_saraswati_lakshmi(c, Strong()) if y.name == "Lakshmi Yoga")
    assert lak.variants == {"phaladipika": False}  # PD 6.24 also wants Venus dignified


def test_bphs_42_dhana_yogas():
    # 42.2: Capricorn lagna, the 5th is Taurus with Venus in it, Mars in the 11th.
    c = make(9, Venus=1, Mars=7)
    (d,) = Y.dhana_yogas(c)
    assert d.source == "dhana_2" and d.grahas == ("Venus", "Mars")
    # 42.9: Leo lagna with the Sun in it, Mars in it and Jupiter aspecting from the 7th.
    c = make(4, Sun=4, Mars=4, Jupiter=10)
    assert [y.source for y in Y.dhana_yogas(c)] == ["dhana_9"]
    c = make(4, Sun=4, Mars=4, Jupiter=11)  # Jupiter in Pisces does not aspect Leo
    assert Y.dhana_yogas(c) == []


def test_nabhasa_exact_houses_and_precedence():
    # All seven in the 1st and 7th: Shakata only. Not also Kamala (4th and 10th
    # empty), Rajju gives way to it (BJ 12.12), and no sankhya (BJ 12.10).
    signs = {"Sun": 0, "Moon": 6, "Mars": 0, "Mercury": 0, "Jupiter": 6, "Venus": 0, "Saturn": 6}
    assert names(Y.nabhasa(make(0, **signs))) == ["Shakata Yoga"]
    # Nothing else: the sankhya yoga by the number of signs held.
    signs = {"Sun": 0, "Moon": 1, "Mars": 2, "Mercury": 0, "Jupiter": 4, "Venus": 1, "Saturn": 7}
    assert names(Y.nabhasa(make(0, **signs))) == ["Pasha Yoga"]
    # Srak: Mercury, Jupiter and Venus in three different kendras.
    signs = {"Sun": 1, "Moon": 11, "Mars": 4, "Mercury": 0, "Jupiter": 3, "Venus": 6, "Saturn": 8}
    assert "Mala (Srak) Yoga" in names(Y.nabhasa(make(0, **signs)))
    signs["Venus"] = 3  # two kendras only
    assert "Mala (Srak) Yoga" not in names(Y.nabhasa(make(0, **signs)))


def test_sources_follow_the_page_map():
    """Research's page map of 19 Oct 2026 (docs/sources/pagemap-2026-10-19.tsv): each cite carries
    every page its verse and translation stand on, and parivartana cites PD 6.32, the verse that
    defines the exchange yogas (6.33 gives the Dainya results)."""
    s = Y.SOURCES
    pages = {k: (s[k]["verse"], s[k]["page"]) for k in s}
    assert pages["mahapurusha_lagna"] == ("6.1", "46–47")
    assert pages["chandra"] == ("6.5", "48–49")
    assert pages["solar"] == ("6.8", "49–50")
    assert pages["parivartana"] == ("6.32", "59–60")
    assert pages["amala"] == ("6.19", "53–54")
    assert pages["lakshmi_pd"] == ("6.24", "55–56")
    assert pages["nabhasa_sankhya"] == ("12.10", "211–212")
    assert [pages[f"dhana_{v}"][1] for v in range(2, 16)] == ["228"] * 9 + ["229"] * 5
