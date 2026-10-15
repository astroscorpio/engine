"""GET|POST /v1/muhurta and /v1/muhurta/check over the engine's muhurta.find/check."""

from __future__ import annotations

import datetime as dt
import re

from jyotisha import muhurta as Mu

from .chart_service import cast
from .errors import invalid
from .fmt import provenance
from .ids import GRAHA_ID, KARANA_ID, MASA_ID, NAKSHATRA_ID, VARA_ID, slug, tithi_id
from .models import ChartIn, MuhurtaCheck, MuhurtaRequest
from .timeutil import iso, local_jd, parse_instant

MAX_DAYS = 31
FINE_DAYS = 7  # minute-by-minute up to a week, 5-minute steps beyond

# Engine rule text -> stable rule id. First match wins, so specific patterns
# come before the general ones they overlap ("Moon in the 8th" before "X in the 8th").
RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(p), rid)
    for p, rid in (
        # House entry (MC 13), first: their labels end in a citation.
        (r"^adhika \w+ \(MC 1\.47\)$", "adhika_masa_home"),
        (r"^\w+: no house entry \(MC 13\.[14]\)$", "month_home"),
        (r"^dakshinayana \(MC (13\.1|5\.26, 5\.29|5\.37)\)$", "dakshinayana"),
        # The first rice (MC 5.17-18; DS pp. 4-5, 135) and the first letters (MC 5.37).
        (r"^adhika \w+ \(DS pp\. 4, 135\)$", "adhika_month_annaprashan"),
        (r"^(Jupiter|Venus) (set|old|infant) \(DS p\. 5\)$", "jupiter_venus_state"),
        (r"^[SK]\d+ \w+: not a first-rice tithi \(DS p\. 135\)$", "tithi_annaprashan"),
        (r"^\w+day: not a first-rice weekday \(MC 5\.17\)$", "weekday_annaprashan"),
        (r"^[\w.]+: not a first-rice star \(DS p\. 135\)$", "nakshatra_annaprashan"),
        (r"^not the forenoon \(Narada, MC 5\.17 commentary\)$", "forenoon_annaprashan"),
        (r"^Vishti, whatever its residence \(DS p\. 135\)$", "vishti_annaprashan"),
        (r"^\w+ yoga, its whole span \(DS p\. 135\)$", "yoga_annaprashan"),
        (r"^\w+ lagna \(MC 5\.17\)$", "lagna_annaprashan"),
        (r"^.+ in the 10th \(MC 5\.18\)$", "house_10_annaprashan"),
        (r"^.+ in the 1st, 4th or 7th \(MC 5\.18\)$", "malefic_annaprashan"),
        (r"^Moon in the \d+\w\w \(MC 5\.18\)$", "moon_6_8_annaprashan"),
        (r"^.+ \(Guru, MC 5\.18 commentary\)$", "guru_7_8_9_annaprashan"),
        (r"^lagna 8th from the child's birth \(MC 5\.17\)$", "lagna_8th_annaprashan"),
        (r"^navamsa 8th from the child's birth \(MC 5\.17; Kashyapa\)$", "navamsa_8th_annaprashan"),
        (r"^month \d+ of life: not for a (boy|girl) \(MC 5\.17; DS p\. 135\)$", "month_of_life"),
        (r"^Sun in Aquarius \(DS p\. 138\)$", "sun_aquarius_akshararambh"),
        (r"^Vishnu asleep, before the Karka sankranti \(MC 5\.37 commentary\)$", "hari_sleeps"),
        (
            r"^[SK]\d+ \w+: not a first-letters tithi \(MC 5\.37; DS p\. 138\)$",
            "tithi_akshararambh",
        ),
        (r"^\w+day: not a first-letters weekday \(MC 5\.37\)$", "weekday_akshararambh"),
        (r"^[\w.]+: not a first-letters star \(MC 5\.37\)$", "nakshatra_akshararambh"),
        (r"^\w+ lagna: not for the first letters \(MC 5\.37\)$", "lagna_akshararambh"),
        (r"^.+ in the 8th \(MC 5\.37 commentary\)$", "house_8_akshararambh"),
        (r"^not the child's 5th year \(MC 5\.37; DS p\. 138\)$", "fifth_year"),
        # The first tonsure (MC 5.26-30).
        (r"^Chaitra: no tonsure \(MC 5\.29\)$", "month_mundan"),
        (r"^(Jupiter|Venus) (set|old|infant) \(MC 5\.26-27\)$", "jupiter_venus_state"),
        (r"^[\w.]+: not a tonsure star \(MC 5\.29\)$", "nakshatra_mundan"),
        (r"^[SK]\d+ \w+: not a tonsure tithi \(MC 5\.29\)$", "tithi_mundan"),
        (r"^\w+day: not a tonsure weekday \(MC 5\.29; Parashara\)$", "weekday_mundan"),
        (r"^\w+ lagna: not a benefic's \(MC 5\.29\)$", "lagna_mundan"),
        (r"^\w+ navamsa: not a benefic's \(MC 5\.29\)$", "navamsa_mundan"),
        (r"^.+ in the 8th \(MC 5\.29\)$", "house_8_mundan"),
        (r"^.+ in a kendra \(MC 5\.30\)$", "kendra_malefic_mundan"),
        (r"^the child's birth star \(DS p\. 137\)$", "birth_star"),
        (r"^the child's birth month \(MC p\. 190\)$", "birth_month"),
        (r"^lagna 8th from the child's birth \(MC 5\.29\)$", "lagna_8th_from_birth_mundan"),
        (r"^Jyeshtha, for an eldest child \(MC 5\.33 commentary\)$", "eldest_jyeshtha"),
        # Buying (MC 2.16-18).
        (r"^[\w.]+: a selling star, barred for buying \(MC 2\.16-17\)$", "selling_star"),
        (r"^\w+day: not a riding weekday \(MC 2\.18 commentary\)$", "riding_weekday"),
        (r"^[\w.]+: not a buying star \(MC 2\.16\)$", "not_buying_star"),
        (r"^(Sunday|Tuesday) \(MC 13\.4\)$", "weekday_home"),
        (r"^middling month for house entry \(Narada\)$", "middling_month_home"),
        (r"^Sun in \w+ \(Guru, MC 13\.1\)$", "sun_sign_home"),
        (r"^(Jupiter|Venus) (set|old|infant) \(MC 1\.46-48, 5\.27\)$", "jupiter_venus_state"),
        (r"^Jupiter in \w+ \(MC 1\.48\)$", "jupiter_sign"),
        (r"^movable lagna \(MC 13\.4\)$", "movable_lagna_home"),
        (r"^movable navamsa \(MC 13\.4\)$", "movable_navamsa"),
        (r"^.+ in the 4th or 8th \(MC 13\.4\)$", "house_4_8_occupied"),
        (r"^Moon in the (1st|6th|12th) \(MC 13\.3-4\)$", "moon_1_6_12"),
        (r"^pot chakra \d+ \(MC 13\.6\)$", "pot_chakra"),
        (r"^tithi not for a [NESW] door \(MC 13\.5\)$", "door_tithi"),
        (r"^Sun not on the left for a [NESW] door \(MC 13\.4-5\)$", "door_sun"),
        # The junctions (MC 6.41; SS 11.21-22) and the lifted kuyogas (MC 1.41-42).
        (r"^Nakshatra gandanta \(MC 6\.41\)$", "nakshatra_gandanta"),
        (r"^Nakshatra junction, within 4 ghatikas \(MC 6\.41\)$", "nakshatra_junction_near"),
        (r"^Nakshatra junction quarter \(SS 11\.21\)$", "nakshatra_junction_quarter"),
        (r"^Lagna gandanta \(MC 6\.41\)$", "lagna_gandanta"),
        (r"^Tithi gandanta \(MC 6\.41\)$", "tithi_gandanta"),
        (r"^\w+ yoga lifted by .+ \(MC 1\.41-42\)$", "kuyoga_lifted"),
        (r"^Ravi yoga \(MC 1\.27\)$", "ravi_yoga"),
        (r"^Rahu kalam$", "rahu_kalam"),
        (r"^Yamaganda$", "yamaganda"),
        (r"^Gulika$", "gulika"),
        (r"^Durmuhurta$", "durmuhurta"),
        (r"^\S+ yoga \((first \d+ ghatis|first half|whole yoga)\)$", "bad_yoga_window"),
        (r"^\S+ yoga, past its opening$", "bad_yoga_after_opening"),
        (r"^Vishti \(Bhadra on earth\)$", "bhadra_earth"),
        (r"^Bhadra's face \(MC 1\.44\)$", "bhadra_face"),
        (r"^Bhadra's tail: no penalty \(MC 1\.44\)$", "bhadra_tail"),
        (r"^Bhadra (by day|at night): no penalty \(MC 1\.44\)$", "bhadra_day_night"),
        (r"^Utpata yoga$", "utpata_yoga"),
        (r"^Kana yoga$", "kana_yoga"),
        (r"^Mahapata \((vyatipata|vaidhriti)\)$", "mahapata"),
        (r"^Siddhi yoga$", "siddhi_yoga"),
        (r"^Visha yoga$", "visha_yoga"),
        (r"^\w+day-[\w.]+ avoided for this act$", "siddhi_pair_act_ban"),
        (r"^Amavasya$", "amavasya"),
        (r"^[SK](4|9|14) \w+$", "rikta_tithi"),
        (r"^[SK]8 \w+$", "ashtami"),
        (r"^Marana yoga$", "marana_yoga"),
        (r"^Dagdha yoga$", "dagdha_yoga"),
        (r"^Moon in the 8th$", "moon_8th"),
        (r"^Chandrashtama$", "chandrashtama"),
        (r"^Moon \d+(st|nd|rd|th) from birth Moon, a good house$", "moon_good_from_birth_moon"),
        (r"^K1 \w+: best for travel \(MC 11\.9 commentary\)$", "travel_best_tithi"),
        (r"^disha shool \w+ on the first leg$", "disha_shool_first_leg"),
        (r"^disha shool \w+$", "disha_shool"),
        (r"^(Vipat|Pratyak|Naidhana) tara$", "bad_tara"),
        (r"^Janma tara$", "janma_tara"),
        (r"^\w+ panchaka$", "panchaka"),
        (r"^\w+ in the 1st$", "malefic_1st"),
        (r"^\w+ in the 7th$", "malefic_7th"),
        (r"^\w+ in the 8th$", "graha_8th"),
        (r"^.+ in the 4th$", "malefic_4th"),
        (r"^lagna 8th from birth$", "lagna_8th_from_birth"),
        (r"^(Udveg|Kaal|Rog) choghadiya$", "bad_choghadiya"),
        (r"^Char choghadiya$", "char_choghadiya"),
        (r"^Moon \d+(st|nd|rd|th) from birth Moon$", "moon_from_birth_moon"),
        (r"^[\w.]+ \(\w+\)$", "nakshatra_unfavoured"),
        (r"^[SK]\d+ \w+$", "tithi_unfavoured"),
        (r"^(Sun|Mon|Tues|Wednes|Thurs|Fri|Satur)day$", "weekday_unfavoured"),
        (r"^adhika \w+$", "adhika_masa"),
        (
            r"^Pitru Paksha: many families avoid new purchases \(popular practice\)$",
            "pitru_paksha_practice",
        ),
        (r"^Moon behind \(Chandra vasa\)$", "moon_behind"),
        (r"^Moon on the left$", "moon_left"),
        (r"^Moon (ahead|on the right)$", "moon_ahead"),
        (r"^Yogini (front|left)$", "yogini_ahead"),  # MC 11.31
        (r"^Yogini (back|right)$", "yogini_behind"),
        (r"^Kharmas$", "kharmas"),
        (r"^Amrita Siddhi$", "amrita_siddhi"),
        (r"^Sarvartha Siddhi$", "sarvartha_siddhi"),
        (r"^lagna lord \w+ strong$", "lagna_lord_strong"),
        (r"^benefic in a kendra$", "benefic_kendra"),
        (r"^Abhijit$", "abhijit"),
        (r"^movable lagna$", "movable_lagna"),
        (r"^fixed lagna$", "fixed_lagna"),
    )
]


def rule_id(label: str, kind: str) -> str:
    if label.endswith(" hora"):
        return "favoured_hora" if kind == "support" else "malefic_hora"
    for pattern, rid in RULES:
        if pattern.match(label):
            return rid
    return slug(label)


def _rows(items: list[tuple[str, float]], kind: str) -> list[dict]:
    return [{"id": rule_id(label, kind), "label": label, "weight": w} for label, w in items]


def _tithi(label: str) -> str:
    """'K10 Dashami' -> 'dashami' with the paksha folded into the number."""
    side, num = label[0], int(label[1:].split()[0])
    return tithi_id(num + (15 if side == "K" else 0))


def facts(f: dict[str, str]) -> dict:
    month = f.get("month", "")
    return {
        "vara": VARA_ID[f["vara"]],
        "tithi": _tithi(f["tithi"]),
        "nakshatra": NAKSHATRA_ID[f["nakshatra"]],
        "yoga": f["yoga"].lower(),
        "karana": KARANA_ID[f["karana"]],
        "lagna": f["lagna"].lower(),
        "hora": GRAHA_ID.get(f.get("hora", ""), None),
        "choghadiya": f.get("choghadiya", "").lower() or None,
        "tara": slug(f["tara"]) if f.get("tara") else None,
        "month": MASA_ID.get(month.removeprefix("Adhika "), slug(month)),
        "adhikaMonth": month.startswith("Adhika "),
    }


def _natal(chart: ChartIn | None):
    """The birth Moon, lagna (None without a birth time) and amanta month name."""
    if chart is None:
        return None, None, None
    c, _ = cast(chart)
    month = Mu.lunar_month(c.jd, c.ayanamsa).name
    return c.grahas["Moon"], (None if chart.timeUnknown else c.asc.sign), month


def _child(req) -> dict | None:
    """The child's birth facts for the samskara acts' own rules, when a chart is given."""
    if req.chart is None or req.act not in ("annaprashan", "akshararambh"):
        return None
    c, _ = cast(req.chart)
    return {
        "birth_jd": c.jd,
        "moon_lon": c.grahas["Moon"].longitude,
        "asc_lon": None if req.chart.timeUnknown else c.asc.longitude,
        "sex": req.child,
    }


def _profile(act: str, toward: str | None) -> Mu.Profile:
    profile = Mu.PROFILES[act]
    if profile.travel and not toward:
        raise invalid("a travel search needs the destination direction", "toward")
    return profile


def find(req: MuhurtaRequest) -> dict:
    profile = _profile(req.act, req.toward)
    days = (req.until - req.from_).days + 1
    if days < 1:
        raise invalid("until must not be before from", "until")
    if days > MAX_DAYS:
        raise invalid(f"the search span is limited to {MAX_DAYS} days", "until")
    start = local_jd(req.from_, 0.0, req.tz, "from")
    end = local_jd(req.until + dt.timedelta(days=1), 0.0, req.tz, "until")
    natal_moon, natal_lagna, natal_month = _natal(req.chart)
    choices = Mu.find(
        profile,
        start,
        end,
        req.lat,
        req.lon,
        natal_moon,
        natal_lagna,
        tz=req.tz,
        hours=Mu.parse_hours(req.hours) if req.hours else None,
        toward=req.toward,
        first_leg=req.firstLeg,
        door=req.door if req.act == "home" else None,
        old_house=req.oldHouse and req.act == "home",
        natal_month=natal_month,
        eldest=req.eldest and req.act == "mundan",
        child=_child(req),
        ayanamsa=req.ayanamsa,
        step_minutes=1 if days <= FINE_DAYS else 5,
    )
    return {
        "act": profile.name,
        "about": profile.about,
        "from": iso(start, req.tz),
        "until": iso(end, req.tz),
        "natalApplied": natal_moon is not None,
        "windows": [
            {
                "start": iso(c.start, req.tz),
                "end": iso(c.end, req.tz),
                "score": round(c.score, 2),
                "facts": facts(c.facts),
                "defects": _rows(c.defects, "defect"),
                "supports": _rows(c.supports, "support"),
                "notes": [{"id": rule_id(label, "note"), "label": label} for label in c.notes],
            }
            for c in choices[: req.top]
        ],
        "engine": provenance(req.ayanamsa),
    }


def check(req: MuhurtaCheck) -> dict:
    profile = _profile(req.act, req.toward)
    jd = parse_instant(req.at, req.tz)
    natal_moon, natal_lagna, natal_month = _natal(req.chart)
    v = Mu.check(
        profile,
        jd,
        req.lat,
        req.lon,
        natal_moon,
        natal_lagna,
        toward=req.toward,
        first_leg=req.firstLeg,
        door=req.door if req.act == "home" else None,
        old_house=req.oldHouse and req.act == "home",
        natal_month=natal_month,
        eldest=req.eldest and req.act == "mundan",
        child=_child(req),
        ayanamsa=req.ayanamsa,
        tz=req.tz,
    )
    return {
        "act": profile.name,
        "at": iso(jd, req.tz),
        "ok": v.ok,
        "score": round(v.score, 2),
        "natalApplied": natal_moon is not None,
        "vetoes": [{"id": rule_id(label, "veto"), "label": label} for label in v.vetoes],
        "defects": _rows(v.defects, "defect"),
        "supports": _rows(v.supports, "support"),
        "notes": [{"id": rule_id(label, "note"), "label": label} for label in v.notes],
        "facts": facts(v.facts),
        "engine": provenance(req.ayanamsa),
    }
