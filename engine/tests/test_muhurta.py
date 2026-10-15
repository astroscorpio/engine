from __future__ import annotations

import pytest

from jyotisha import muhurta as M
from jyotisha.ephemeris import NAKSHATRAS, jd, sunrise
from jyotisha.subjects import SUBJECTS

# EXAMPLE's observer, Paris; the expected windows below are for it.
SAMPLE_PLACE = (48.8566, 2.3522)


@pytest.fixture(scope="module")
def sunday():
    return M.day(jd(2026, 9, 20, 12.0, 2.0), *SAMPLE_PLACE)


def test_sunrise_just_before_dawn_is_the_previous_one() -> None:
    sr = sunrise(jd(2026, 9, 20, 12.0, 2.0), *SAMPLE_PLACE)
    assert sunrise(sr - 1e-3, *SAMPLE_PLACE) < sr - 0.9
    assert sunrise(sr, *SAMPLE_PLACE) == pytest.approx(sr)


def test_brahma_muhurta_ends_one_night_muhurta_before_sunrise(sunday) -> None:
    night_muhurta = (sunday.sunrise - sunday.prev_sunset) / 15
    assert sunday.brahma.end == pytest.approx(sunday.sunrise - night_muhurta)
    assert sunday.prev_sunset < sunday.brahma.start < sunday.brahma.end < sunday.sunrise


def test_sunday_kalams_are_the_right_eighths(sunday) -> None:
    eighth = (sunday.sunset - sunday.sunrise) / 8
    got = {w.label: round((w.start - sunday.sunrise) / eighth) + 1 for w in sunday.avoid[:3]}
    assert got == {"Rahu kalam": 8, "Yamaganda": 5, "Gulika": 7}


def test_hora_and_choghadiya_start_from_the_weekday_lord(sunday) -> None:
    assert sunday.vara == "Sun"
    assert [w.label for w in sunday.horas[:3]] == ["Sun", "Venus", "Mercury"]
    day_names = [w.label for w in sunday.choghadiyas[:8]]
    night_names = [w.label for w in sunday.choghadiyas[8:]]
    assert day_names == ["Udveg", "Char", "Labh", "Amrit", "Kaal", "Shubh", "Rog", "Udveg"]
    assert night_names == ["Shubh", "Amrit", "Char", "Rog", "Kaal", "Labh", "Udveg", "Shubh"]
    assert sunday.choghadiyas[8].start == pytest.approx(sunday.sunset)


def test_lagna_windows_tile_the_day(sunday) -> None:
    spans = sunday.lagnas
    assert spans[0].start == pytest.approx(sunday.brahma.start)
    assert spans[-1].end == pytest.approx(sunday.next_sunrise)
    for a, b in zip(spans, spans[1:], strict=False):
        assert a.end == pytest.approx(b.start)
        assert a.label != b.label


def test_rule_tables() -> None:
    anuradha, shravana = NAKSHATRAS.index("Anuradha"), NAKSHATRAS.index("Shravana")
    assert M.tara(anuradha, shravana) == "Sadhana"
    assert M.siddha_yoga(12, "Mercury") and not M.siddha_yoga(11, "Mars")
    assert M.commencement(11, "Mars", shravana) == {
        "vara": False,
        "tithi": True,
        "nakshatra": True,
    }
    assert M.yogini_direction(1) == "E" and M.yogini_direction(9) == "E"
    assert M.relative_side("N", "E") == "right"
    assert M.relative_side("N", "S") == "back"
    assert M.bhadra_residence(9) == "patala"  # Moon in Capricorn


def test_opening_ghatis_of_shula_yoga_are_avoided() -> None:
    thursday = M.day(jd(2026, 9, 24, 13.0, 2.0), *SAMPLE_PLACE)
    shula = [w for w in thursday.avoid if w.label.startswith("Shula")]
    assert len(shula) == 1
    assert (shula[0].end - shula[0].start) * 1440 == pytest.approx(5 * 24, abs=0.01)
    assert M.yoga_at(shula[0].start + 1e-4) == M.YOGA_NAMES.index("Shula")


BIRTH = (lambda c: (c.grahas["Moon"], c.asc.sign))(SUBJECTS["example"].chart())


def _check(act: str, y: int, mo: int, d: int, hour: float, **kw) -> M.Verdict:
    return M.check(M.PROFILES[act], jd(y, mo, d, hour, 2.0), *SAMPLE_PLACE, *BIRTH, **kw)


def _labels(v: M.Verdict) -> set[str]:
    return {label for label, _ in v.defects + v.supports}


def test_lunar_month_follows_the_ingress_and_finds_adhika() -> None:
    # 2026 carries an adhika Jyeshtha, so September's month is Bhadrapada.
    assert M.lunar_month(jd(2026, 9, 17, 12.0, 2.0)).label == "Bhadrapada"
    assert M.lunar_month(jd(2026, 5, 25, 12.0, 2.0)).label == "Adhika Jyeshtha"
    assert M.lunar_month(jd(2026, 10, 15, 12.0, 2.0)).label == "Ashwin"


def test_bhadra_in_patala_costs_nothing_but_gulika_still_vetoes() -> None:
    # Vishti ran all morning with the Moon in Capricorn: Bhadra was below, and
    # "its effect falls there" (MC 1.45), so no penalty. The Amrit choghadiya
    # coincides with Gulika, as it does every Tuesday.
    v = _check("general", 2026, 9, 22, 14.0)
    assert v.vetoes == ["Gulika"]
    assert not any(label.startswith("Vishti") for label in _labels(v))


def test_durmuhurta_vetoes_a_moment_the_kalams_allow() -> None:
    assert "Durmuhurta" in _check("general", 2026, 9, 17, 12 + 10 / 60).vetoes


def test_sunday_hasta_is_amrita_and_sarvartha_siddhi() -> None:
    v = _check("general", 2026, 9, 13, 9 + 25 / 60)
    assert v.ok and {"Amrita Siddhi", "Sarvartha Siddhi"} <= _labels(v)


def test_journey_rules_read_direction_and_season() -> None:
    westward = {"toward": "W", "first_leg": "S"}
    assert _check("travel", 2026, 9, 27, 12 + 40 / 60, **westward).vetoes == ["disha shool W"]
    monday = _check("travel", 2026, 9, 28, 11 + 40 / 60, **westward)
    assert monday.ok
    # No text read penalises Pitru Paksha (the lead's ruling of 15 Oct 2026).
    assert {"Moon behind (Chandra vasa)", "Vipat tara"} <= _labels(monday)
    assert not any("Pitru" in label for label in _labels(monday)) and not monday.notes
    thursday = _check("travel", 2026, 9, 24, 14 + 45 / 60, **westward)
    assert {"Moon ahead", "disha shool S on the first leg"} <= _labels(thursday)
    assert thursday.score < monday.score


def test_find_ranks_the_clean_evening_window_first() -> None:
    general = M.PROFILES["general"]
    span = jd(2026, 9, 22, 18.0, 2.0), jd(2026, 9, 22, 23.0, 2.0)
    best = M.find(general, *span, *SAMPLE_PLACE, *BIRTH, tz=2.0)[0]
    assert best.start <= jd(2026, 9, 22, 21 + 42 / 60, 2.0) < best.end
    assert best.facts["lagna"] == "Taurus"


def test_almanac_yogini_swaps_chaturthi_and_saptami() -> None:
    assert M.yogini_direction(4) == "SW" and M.yogini_direction(7) == "NW"
    assert M.resolve_direction("276") == "W" and M.resolve_direction("nw") == "NW"
