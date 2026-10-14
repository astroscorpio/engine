"""GET /v1/meta: display names for every id the API emits.

Everything here is either read from the engine's own tables or is a plain
name. Fields that need a cited source (nakshatra deity, symbol, gana, nadi,
yoni) stay null until docs/sources/ supplies them.
"""

from __future__ import annotations

from functools import cache

from jyotisha import __version__ as ENGINE_VERSION
from jyotisha import muhurta as Mu
from jyotisha.chart import BENEFICS, MALEFICS, SIGN_LORDS
from jyotisha.ephemeris import NAKSHATRAS, SIGNS
from jyotisha.panchanga import FIXED_KARANAS, KARANA_NAMES, YOGA_NAMES
from jyotisha.vargas import VARGA_NAMES, VARGA_SIGNIFIES

from . import avakahada as AV
from . import matching as M
from .errors import invalid
from .fmt import SOURCE_URL, _ephemeris_backend
from .ids import (
    GRAHA_ID,
    KARANA_ID,
    MASA_ID,
    NAKSHATRA_IDS,
    NAKSHATRA_LORD,
    SIGN_IDS,
    TITHI_BASE,
    VARA_ID,
    YOGA_IDS,
    slug,
)
from .muhurta_service import RULES

GRAHA_SANSKRIT = {
    "sun": "Surya", "moon": "Chandra", "mars": "Mangala", "mercury": "Budha",
    "jupiter": "Guru", "venus": "Shukra", "saturn": "Shani", "rahu": "Rahu", "ketu": "Ketu",
}  # fmt: skip
GRAHA_GLYPH = {
    "sun": "☉", "moon": "☽", "mars": "♂", "mercury": "☿", "jupiter": "♃",
    "venus": "♀", "saturn": "♄", "rahu": "☊", "ketu": "☋",
}  # fmt: skip
SIGN_SANSKRIT = [
    "Mesha", "Vrishabha", "Mithuna", "Karka", "Simha", "Kanya",
    "Tula", "Vrishchika", "Dhanu", "Makara", "Kumbha", "Meena",
]  # fmt: skip
NAKSHATRA_DISPLAY = {
    "P.Phalguni": "Purva Phalguni", "U.Phalguni": "Uttara Phalguni",
    "P.Ashadha": "Purva Ashadha", "U.Ashadha": "Uttara Ashadha",
    "P.Bhadrapada": "Purva Bhadrapada", "U.Bhadrapada": "Uttara Bhadrapada",
}  # fmt: skip
VARA_SANSKRIT = {
    "sunday": "Ravivara", "monday": "Somavara", "tuesday": "Mangalavara",
    "wednesday": "Budhavara", "thursday": "Guruvara", "friday": "Shukravara",
    "saturday": "Shanivara",
}  # fmt: skip
TITHI_DISPLAY = {
    "pratipada": "Pratipada", "dwitiya": "Dwitiya", "tritiya": "Tritiya",
    "chaturthi": "Chaturthi", "panchami": "Panchami", "shashthi": "Shashthi",
    "saptami": "Saptami", "ashtami": "Ashtami", "navami": "Navami", "dashami": "Dashami",
    "ekadashi": "Ekadashi", "dwadashi": "Dwadashi", "trayodashi": "Trayodashi",
    "chaturdashi": "Chaturdashi", "purnima": "Purnima", "amavasya": "Amavasya",
}  # fmt: skip

WINDOWS = {
    "brahma": ("Brahma Muhurta", "The second-last muhurta of the night, ending one muhurta before sunrise."),
    "abhijit": ("Abhijit Muhurta", "The eighth of the fifteen daytime muhurtas, around local noon; not used on Wednesdays."),
    "pradosha": ("Pradosha", "The three muhurtas after sunset."),
    "rahu_kalam": ("Rahu Kalam", "One eighth of the daylight, fixed by weekday; avoided for beginnings."),
    "yamaganda": ("Yamaganda", "Jupiter's eighth of the daylight; avoided for beginnings."),
    "gulika": ("Gulika Kalam", "Saturn's eighth of the daylight; avoided for beginnings."),
    "durmuhurta": ("Durmuhurta", "Daytime muhurtas marked inauspicious for the weekday."),
    "bad_yoga": ("Inauspicious yoga", "The opening ghatis (or all) of Vishkambha, Atiganda, Shula, Ganda, Vyaghata, Vajra, Parigha, Vyatipata and Vaidhriti."),
    "vishti": ("Bhadra (Vishti karana)", "Vishti karana; harmful while Bhadra resides on earth (Moon in Cancer, Leo, Aquarius or Pisces)."),
}  # fmt: skip

DIGNITIES = {
    "exalted": "Exalted", "moolatrikona": "Moolatrikona", "own": "Own sign",
    "great_friend": "Great friend", "friend": "Friend", "neutral": "Neutral",
    "enemy": "Enemy", "great_enemy": "Great enemy", "debilitated": "Debilitated",
}  # fmt: skip
YOGA_CATEGORIES = {
    "mahapurusha": "Pancha Mahapurusha", "raja": "Raja yoga", "dhana": "Dhana yoga",
    "vipareeta": "Vipareeta Raja yoga", "cancellation": "Neecha Bhanga", "lunar": "Lunar yoga",
    "solar": "Solar yoga", "exchange": "Parivartana", "dosha": "Dosha",
    "auspicious": "Auspicious yoga", "nabhasa": "Nabhasa yoga",
}  # fmt: skip
SPECIAL_YOGAS = {
    "amrita_siddhi": "Amrita Siddhi", "sarvartha_siddhi": "Sarvartha Siddhi",
    "siddha": "Siddha", "marana": "Marana", "dagdha": "Dagdha",
}  # fmt: skip
AYANAMSAS = {
    "lahiri": "Lahiri (Chitrapaksha)", "raman": "B. V. Raman", "krishnamurti": "Krishnamurti (KP)",
    "true_citra": "True Chitra", "true_revati": "True Revati", "yukteshwar": "Sri Yukteshwar",
    "suryasiddhanta": "Surya Siddhanta", "fagan_bradley": "Fagan-Bradley", "tropical": "Tropical (none)",
}  # fmt: skip
STATES = {
    "baladi": ["bala", "kumara", "yuva", "vriddha", "mrita"],
    "jagradadi": ["jagrat", "swapna", "sushupti"],
    "deeptadi": ["deepta", "swastha", "pramudita", "shanta", "deena", "dukhita", "vikala", "khala", "kopa"],
    "lajjitadi": ["lajjita", "garvita", "kshudita", "trishita", "mudita", "kshobhita"],
}  # fmt: skip
CHARA_KARAKAS = {
    "ak": "Atmakaraka", "amk": "Amatyakaraka", "bk": "Bhratrikaraka", "mk": "Matrikaraka",
    "pik": "Pitrikaraka", "pk": "Putrakaraka", "gk": "Gnatikaraka", "dk": "Darakaraka",
}  # fmt: skip

# Known yoga ids with their category (see chart_service.yoga_id).
YOGAS = {
    "ruchaka": ("Ruchaka", "mahapurusha"), "bhadra": ("Bhadra", "mahapurusha"),
    "hamsa": ("Hamsa", "mahapurusha"), "malavya": ("Malavya", "mahapurusha"),
    "sasa": ("Sasa", "mahapurusha"), "raja": ("Raja Yoga", "raja"),
    "raja_single_lord": ("Raja Yoga (single lord)", "raja"), "dhana": ("Dhana Yoga", "dhana"),
    "harsha": ("Harsha", "vipareeta"), "sarala": ("Sarala", "vipareeta"),
    "vimala": ("Vimala", "vipareeta"), "neecha_bhanga_raja": ("Neecha Bhanga Raja Yoga", "cancellation"),
    "durudhara": ("Durudhara", "lunar"), "sunapha": ("Sunapha", "lunar"),
    "anapha": ("Anapha", "lunar"), "kemadruma": ("Kemadruma", "lunar"),
    "gaja_kesari": ("Gaja Kesari", "lunar"), "chandra_mangala": ("Chandra-Mangala", "lunar"),
    "adhi": ("Adhi", "lunar"), "shakata": ("Shakata", "lunar"),
    "ubhayachari": ("Ubhayachari", "solar"), "vesi": ("Vesi", "solar"), "vasi": ("Vasi", "solar"),
    "budha_aditya": ("Budha-Aditya", "solar"),
    "dainya_parivartana": ("Dainya Parivartana", "exchange"),
    "khala_parivartana": ("Khala Parivartana", "exchange"),
    "maha_parivartana": ("Maha Parivartana", "exchange"),
    "kuja_dosha": ("Kuja (Mangal) Dosha (Khankhoje 1943)", "dosha"),
    "kala_sarpa": ("Kala Sarpa", "dosha"), "amala": ("Amala", "auspicious"),
    "saraswati": ("Saraswati", "auspicious"), "lakshmi": ("Lakshmi", "auspicious"),
    "gola": ("Gola", "nabhasa"), "yuga": ("Yuga", "nabhasa"), "shoola": ("Shoola", "nabhasa"),
    "kedara": ("Kedara", "nabhasa"), "pasha": ("Pasha", "nabhasa"), "damini": ("Damini", "nabhasa"),
    "veena": ("Veena", "nabhasa"), "rajju": ("Rajju", "nabhasa"), "musala": ("Musala", "nabhasa"),
    "nala": ("Nala", "nabhasa"), "mala": ("Mala (Srak)", "nabhasa"), "sarpa": ("Sarpa", "nabhasa"),
    "kamala": ("Kamala", "nabhasa"), "shringataka": ("Shringataka", "nabhasa"),
    "shakata_akriti": ("Shakata (akriti)", "nabhasa"), "vihaga": ("Vihaga", "nabhasa"),
    "hala": ("Hala", "nabhasa"), "vapi": ("Vapi", "nabhasa"), "yupa": ("Yupa", "nabhasa"),
    "shara": ("Shara", "nabhasa"), "shakti": ("Shakti", "nabhasa"), "danda": ("Danda", "nabhasa"),
    "nauka": ("Nauka", "nabhasa"), "kuta": ("Kuta", "nabhasa"), "chhatra": ("Chhatra", "nabhasa"),
    "chapa": ("Chapa", "nabhasa"), "chakra": ("Chakra", "nabhasa"), "samudra": ("Samudra", "nabhasa"),
}  # fmt: skip

MUHURTA_RULE_NAMES = {
    "rahu_kalam": "Rahu Kalam", "yamaganda": "Yamaganda", "gulika": "Gulika Kalam",
    "durmuhurta": "Durmuhurta", "bad_yoga_window": "Inauspicious yoga (opening ghatis)",
    "bad_yoga_after_opening": "Inauspicious yoga, past its opening",
    "bhadra_earth": "Bhadra on earth", "bhadra_elsewhere": "Bhadra (not on earth)",
    "amavasya": "Amavasya", "rikta_tithi": "Rikta tithi (4th, 9th, 14th)", "ashtami": "Ashtami",
    "marana_yoga": "Marana yoga", "dagdha_yoga": "Dagdha yoga", "moon_8th": "Moon in the 8th",
    "chandrashtama": "Chandrashtama", "disha_shool": "Disha shool",
    "disha_shool_first_leg": "Disha shool on the first leg", "bad_tara": "Inauspicious tara",
    "janma_tara": "Janma tara", "panchaka": "Panchaka", "malefic_1st": "Malefic in the 1st",
    "malefic_7th": "Malefic in the 7th", "graha_8th": "Graha in the 8th",
    "malefic_4th": "Malefic in the 4th", "lagna_8th_from_birth": "Lagna 8th from birth",
    "bad_choghadiya": "Inauspicious choghadiya", "char_choghadiya": "Char choghadiya",
    "moon_from_birth_moon": "Moon 4th or 12th from the birth Moon",
    "nakshatra_unfavoured": "Nakshatra not favoured for this act",
    "tithi_unfavoured": "Tithi not favoured for this act",
    "weekday_unfavoured": "Weekday not favoured for this act", "adhika_masa": "Adhika masa",
    "pitru_paksha": "Pitru Paksha", "moon_behind": "Moon behind (Chandra vasa)",
    "moon_left": "Moon on the left", "moon_ahead": "Moon ahead or on the right",
    "yogini_ahead": "Yogini ahead or on the right", "yogini_behind": "Yogini behind or on the left",
    "kharmas": "Kharmas", "amrita_siddhi": "Amrita Siddhi", "sarvartha_siddhi": "Sarvartha Siddhi",
    "lagna_lord_strong": "Lagna lord strong", "benefic_kendra": "Benefic in a kendra",
    "abhijit": "Abhijit muhurta", "movable_lagna": "Movable lagna", "fixed_lagna": "Fixed lagna",
    "favoured_hora": "Favoured hora", "malefic_hora": "Mars or Saturn hora",
}  # fmt: skip
VETOES = {
    "rahu_kalam", "yamaganda", "gulika", "durmuhurta", "bad_yoga_window", "bhadra_earth",
    "amavasya", "rikta_tithi", "ashtami", "marana_yoga", "dagdha_yoga", "moon_8th",
    "chandrashtama", "disha_shool",
}  # fmt: skip
SUPPORTS = {
    "amrita_siddhi", "sarvartha_siddhi", "lagna_lord_strong", "benefic_kendra", "abhijit",
    "moon_ahead", "yogini_behind", "char_choghadiya", "movable_lagna", "fixed_lagna",
    "favoured_hora",
}  # fmt: skip


KUJA_CONVENTIONS = {
    "second_house": "Mars in the 2nd from the lagna (common practice, source pending)",
    "from_moon": "Mars in the 1st, 2nd, 4th, 7th, 8th or 12th from the Moon (common practice, source pending)",
    "from_venus": "Mars in the 1st, 2nd, 4th, 7th, 8th or 12th from Venus (common practice, source pending)",
}
MATCHING_BASES = {"chart": "Birth details", "nakshatra": "Birth star", "name": "Name"}
NAME_RULES = {
    "conjunct_first_letter": "A conjunct is read by its first letter",
    "equivalent_letters": "Ba and va, śa and sa, kha and ṣa stand for each other when a syllable is missing",
    "nasal_read_as": "Names in ṅa, ña and ṇa are read as ga, ja and ḍa",
    "abhijit_as_uttara_ashadha": "Abhijit's syllables count as Uttarashadha pada 4",
}
KOOTA_NAMES = {
    "varna": "Varna", "vashya": "Vashya", "tara": "Tara", "yoni": "Yoni",
    "graha_maitri": "Graha Maitri", "gana": "Gana", "bhakoot": "Bhakoot", "nadi": "Nadi",
}  # fmt: skip
VARNAS = {
    "brahmana": "Brahmana",
    "kshatriya": "Kshatriya",
    "vaishya": "Vaishya",
    "shudra": "Shudra",
}
GANAS = {"deva": "Deva", "manushya": "Manushya", "rakshasa": "Rakshasa"}
VASHYA_GROUP_NAMES = {
    "chatushpada": "Chatushpada (quadruped)", "manava": "Manava (human)",
    "jalachara": "Jalachara (water)", "vanachara": "Vanachara (forest)", "keeta": "Keeta (insect)",
}  # fmt: skip
NADIS = {"adi": "Adi", "madhya": "Madhya", "antya": "Antya"}
MATCHING_NOTES = {
    "same_sign_different_nakshatra": "Same Moon sign, different nakshatra: no nadi or gana dosha (MC 6.36)",
    "same_nakshatra_different_sign": "Same nakshatra, different Moon signs: no nadi or gana dosha (MC 6.36)",
    "same_nakshatra_different_pada": "Same nakshatra, different pada: auspicious (MC 6.36)",
    "same_nakshatra_same_pada": "Same nakshatra and pada: held fatal (Narada; MM v.6)",
    "tara_clear_same_sign": "Same Moon sign: no tara fault (MC 6.36 commentary)",
    "sign_lords_friendly": "The Moon-sign lords are friends (MC 6.33, p. 256)",
    "navamsha_lords_friendly": "The Moons' navamsha lords are friends (MC 6.33)",
    "same_sign_lord": "Both Moon signs have the same lord (MC p. 256)",
    "tara_pure_both_ways": "Tara is pure both ways (Rajamartanda, in MC p. 255)",
    "navamsha_lords_friendly_strength_not_assessed":
        "The navamsha lords are friends, but their strength (MC p. 256) is not assessed",
    "moon_uncertain_birth_time_unknown": "Birth time unknown and the Moon changed sign or star that day",
    "our_reading_of_bjs": "Vashya groups and points are our reading of Brihat Jyotishsara (1892)",
    "vashya_group_uncertain": "The birth-star pada spans 15 degrees of Sagittarius or Capricorn, so the vashya group is open",
}  # fmt: skip
for _rid in ("same_sign_lord", "sign_lords_friendly", "tara_pure_both_ways"):
    MATCHING_NOTES[f"{_rid}_but_nadi_dosha"] = MATCHING_NOTES[_rid] + ", but nadi is not clear"


def engine_info() -> dict:
    return {
        "name": "jyotisha",
        "version": ENGINE_VERSION,
        "ephemeris": _ephemeris_backend(),
        "source": SOURCE_URL,
    }


def _nature(graha: str) -> str:
    if graha in BENEFICS:
        return "benefic"
    if graha in MALEFICS:
        return "malefic"
    return "neutral"


@cache
def _english() -> dict:
    grahas = {
        GRAHA_ID[g]: {
            "name": g,
            "sanskrit": GRAHA_SANSKRIT[GRAHA_ID[g]],
            "glyph": GRAHA_GLYPH[GRAHA_ID[g]],
            "nature": _nature(g),
        }
        for g in GRAHA_ID
    }
    signs = {
        SIGN_IDS[i]: {
            "name": SIGNS[i],
            "sanskrit": SIGN_SANSKRIT[i],
            "num": i + 1,
            "lord": GRAHA_ID[SIGN_LORDS[i]],
            "element": ("fire", "earth", "air", "water")[i % 4],
            "modality": ("movable", "fixed", "dual")[i % 3],
        }
        for i in range(12)
    }
    nakshatras = {
        NAKSHATRA_IDS[i]: {
            "name": NAKSHATRA_DISPLAY.get(NAKSHATRAS[i], NAKSHATRAS[i]),
            "num": i + 1,
            "lord": NAKSHATRA_LORD[i],
            "start": round(i * 360 / 27, 6),
            # gana, nadi and yoni: MC 6.29, 6.34 and 6.25-26 (see matching.py).
            # deity and symbol stay null until docs/sources/ supplies them.
            "deity": None,
            "symbol": None,
            "gana": M.GANA_OF_NAKSHATRA[i],
            "nadi": M.NADI_OF_NAKSHATRA[i],
            "yoni": M.YONI_OF_NAKSHATRA[i],
        }
        for i in range(27)
    }
    tithis = {
        tid: {"name": TITHI_DISPLAY[tid], "num": [n for n in range(1, 31) if _tithi_of(n) == tid]}
        for tid in [*TITHI_BASE, "purnima", "amavasya"]
    }
    bad_yogas = set(Mu.BAD_YOGA_GHATIS)
    return {
        "lang": "en",
        "grahas": grahas,
        "signs": signs,
        "nakshatras": nakshatras,
        "tithis": tithis,
        "panchangYogas": {
            YOGA_IDS[i]: {
                "name": YOGA_NAMES[i],
                "num": i + 1,
                "inauspicious": YOGA_NAMES[i] in bad_yogas,
            }
            for i in range(27)
        },
        "karanas": {
            KARANA_ID[k]: {"name": k, "fixed": k in FIXED_KARANAS}
            for k in KARANA_NAMES + FIXED_KARANAS
        },
        "varas": {
            VARA_ID[lord]: {
                "name": Mu.VARA_NAME[lord],
                "sanskrit": VARA_SANSKRIT[VARA_ID[lord]],
                "lord": GRAHA_ID[lord],
            }
            for lord in VARA_ID
        },
        "masas": {MASA_ID[m]: {"name": m, "num": i + 1} for i, m in enumerate(Mu.MASA)},
        "choghadiya": {
            name.lower(): {
                "name": name,
                "quality": {"Char": "neutral"}.get(
                    name, "good" if name in Mu.CHOGHADIYA_GOOD else "avoid"
                ),
            }
            for name in ("Amrit", "Shubh", "Labh", "Char", "Udveg", "Kaal", "Rog")
        },
        "windows": {k: {"name": n, "description": d} for k, (n, d) in WINDOWS.items()},
        "specialYogas": {k: {"name": v} for k, v in SPECIAL_YOGAS.items()},
        "dignities": {k: {"name": v} for k, v in DIGNITIES.items()},
        "yogaCategories": {k: {"name": v} for k, v in YOGA_CATEGORIES.items()},
        "yogas": {k: {"name": n, "category": c} for k, (n, c) in YOGAS.items()},
        "vargas": {
            f"D{d}": {"name": VARGA_NAMES[d], "signifies": VARGA_SIGNIFIES[d]} for d in VARGA_NAMES
        },
        "states": {
            group: {sid: {"name": sid.capitalize()} for sid in ids} for group, ids in STATES.items()
        },
        "charaKarakas": {k: {"name": v} for k, v in CHARA_KARAKAS.items()},
        "muhurtaActs": {
            name: {"name": name.capitalize(), "about": p.about} for name, p in Mu.PROFILES.items()
        },
        "muhurtaRules": {
            rid: {
                "name": MUHURTA_RULE_NAMES[rid],
                "kind": "veto" if rid in VETOES else "support" if rid in SUPPORTS else "defect",
            }
            for rid in sorted({rid for _, rid in RULES} | {"favoured_hora", "malefic_hora"})
        },
        "ayanamsas": {k: {"name": v} for k, v in AYANAMSAS.items()},
        "kootas": {
            k: {"name": KOOTA_NAMES[k], "max": M.MAX[k], "source": M.SOURCES[k]} for k in M.MAX
        },
        "varnas": {k: {"name": v} for k, v in VARNAS.items()},
        "yonis": {y: {"name": y.capitalize()} for y in M.YONIS},
        "ganas": {k: {"name": v} for k, v in GANAS.items()},
        "vashyaGroups": {k: {"name": v} for k, v in VASHYA_GROUP_NAMES.items()},
        "nadis": {k: {"name": v} for k, v in NADIS.items()},
        "taras": {slug(t): {"name": t, "num": i + 1} for i, t in enumerate(Mu.TARA_NAMES)},
        "matchingNotes": {k: {"name": v} for k, v in MATCHING_NOTES.items()},
        "matchingBases": {k: {"name": v} for k, v in MATCHING_BASES.items()},
        "avakahada": {
            "source": AV.SOURCE,
            "chakra": AV.CHAKRA,
            "abhijit": {
                "name": "Abhijit",
                "nakshatra": AV.ABHIJIT[0],
                "pada": AV.ABHIJIT[1],
                "source": AV.RULES["abhijit_as_uttara_ashadha"],
            },
            "rules": {k: {"name": NAME_RULES[k], "source": src} for k, src in AV.RULES.items()},
        },
        "kujaConventions": {k: {"name": v} for k, v in KUJA_CONVENTIONS.items()},
    }


def _tithi_of(num: int) -> str:
    from .ids import tithi_id

    return tithi_id(num)


def dictionary(lang: str = "en") -> dict:
    if lang != "en":
        raise invalid("only lang=en is available", "lang")
    return _english()
