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
from .observances import EKADASHI_NAMES, EM, NAME_NOTES, NS_P51

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
    "bad_yoga": ("Inauspicious yoga", "The opening ghatis of Vishkambha (3), Vajra (3), Shula (5), Ganda and Atiganda (6) and Vyaghata (9), the first half of Parigha, and all of Vyatipata and Vaidhriti."),
    "vishti": ("Bhadra (Vishti karana)", "Vishti karana, avoided while Bhadra resides on earth (Moon in Cancer, Leo, Aquarius or Pisces). Elsewhere its effect falls in that world."),
}  # fmt: skip
# docs/sources/methodology.md and panchang-yogas.md.
WINDOW_SOURCES = {
    "rahu_kalam": "Kalaprakasika, tr. N. P. Subramania Iyer, 1917, pp. 175-176",
    "yamaganda": "Kalaprakasika, tr. N. P. Subramania Iyer, 1917, pp. 175-176",
    "gulika": "Kalaprakasika, tr. N. P. Subramania Iyer, 1917, pp. 175-176",
    "durmuhurta": "Muhurta Chintamani 6.52, p. 275",
    "abhijit": "Muhurta Chintamani 6.50, p. 274 (the 8th day muhurta); 6.52, p. 275 (not on Wednesday)",
    "bad_yoga": "Muhurta Chintamani 1.34-35, p. 28; Nirnaya-sindhu p. 33 (Muhurta Martanda v.2 gives Vajra 9)",
    "vishti": "Muhurta Chintamani 1.43-45, pp. 35-38",
    "pradosha": "Muhurta Chintamani 3.6 commentary, p. 125 (Skanda); Nirnaya-sindhu p. 29; Viramitrodaya, Samaya-prakasha, p. 129",
}
WINDOW_NOTES = {
    "pradosha": "Three muhurtas after sunset, a muhurta being a fifteenth of the night (MC 6.50-51; our reading). The first 72 minutes are sandhya, the evening twilight (Nirnaya-sindhu p. 29, Skanda). The Gauda view of two ghatikas (48 minutes) is rejected for vows by Nirnaya-sindhu p. 29.",
    "brahma": "The 14th night muhurta is the computed convention; a printed source for that placement is pending. The name is from Manusmriti 4.92.",
}
# MC 1.45 (p. 38): "bhadra tatraiva tatphalam", its effect falls where it resides.
BHADRA_RESIDENCES = {
    "earth": ("On earth (martya)", "With the Moon in Cancer, Leo, Aquarius or Pisces, Bhadra is on earth, and its effect falls here."),
    "heaven": ("In heaven (svarga)", "With the Moon in Aries, Taurus, Gemini or Scorpio, Bhadra is in heaven, and its effect falls there."),
    "patala": ("Below (patala)", "With the Moon in Virgo, Sagittarius, Libra or Capricorn, Bhadra is below, and its effect falls there."),
}  # fmt: skip

DIGNITIES = {
    "exalted": "Exalted", "moolatrikona": "Moolatrikona", "own": "Own sign",
    "great_friend": "Great friend", "friend": "Friend", "neutral": "Neutral",
    "enemy": "Enemy", "great_enemy": "Great enemy", "debilitated": "Debilitated",
}  # fmt: skip
PAKSHAS = {"shukla": "Shukla", "krishna": "Krishna"}
DASHA_LEVELS = {
    "1": "Mahadasha", "2": "Antardasha", "3": "Pratyantardasha", "4": "Sookshma dasha",
    "5": "Prana dasha",
}  # fmt: skip
# Nirnaya-sindhu, 1898 printing (docs/sources/observances.md); observances.py.
EKADASHI_TRADITIONS = {"smarta": "Smārta", "vaishnava": "Vaiṣṇava (Nirṇaya-sindhu)"}
EKADASHI_RULES = {
    "smarta": {
        "sunrise": ("Ekādaśī at sunrise: that day", "Nirnaya-sindhu p. 58"),
        "ekadashi_increases": ("Ekādaśī runs long, Dvādaśī does not: householders keep the first day, ascetics the second (Skanda)", "Nirnaya-sindhu p. 59"),
        "dvadashi_increases": ("Only Dvādaśī runs long, Ekādaśī pure: the first day (Mādhava)", "Nirnaya-sindhu p. 60"),
        "both_increase": ("Ekādaśī and Dvādaśī both run long: everyone keeps the second day (Nārada, Mādhava)", "Nirnaya-sindhu pp. 59-60"),
        "no_dvadashi_next_day": ("Ekādaśī at no sunrise and no Dvādaśī at the next: everyone keeps the pierced day (Skanda, Ṛṣyaśṛṅga)", "Nirnaya-sindhu pp. 60, 62"),
        "viddha_nyuna_householders_first": ("Ekādaśī at no sunrise, Dvādaśī over before the following one: householders keep the pierced day, ascetics and those seeking liberation the next (Madana-ratna; Mādhava). Madana-ratna gives the pierced day to those with sons too", "Nirnaya-sindhu p. 62"),
        "viddha_nyuna_dvadashi_long": ("Ekādaśī at no sunrise, Dvādaśī still current at the following one: everyone keeps the next day", "Nirnaya-sindhu p. 60"),
    },
    "vaishnava": {
        "pure": ("No Daśamī in the 96 minutes before sunrise: that day", "Nirnaya-sindhu p. 53"),
        "arunodaya_pierced": ("Daśamī within the 96 minutes before sunrise (aruṇodaya): the next day (Garuḍa)", "Nirnaya-sindhu p. 53"),
        "increase": ("Ekādaśī or Dvādaśī runs long: the later day (Mādhava)", "Nirnaya-sindhu p. 59"),
        "pierced_next_day": ("Ekādaśī at no sunrise: the pure Dvādaśī day", "Nirnaya-sindhu pp. 53, 62-63"),
    },
}  # fmt: skip
OBSERVANCE_RULES = {
    "vrata": {
        "later_day": ("The later day, joined to the next Pratipada; never the day joined to Chaturdashi (Brahma-vaivarta). The Savitri vrata keeps the earlier day", "Nirnaya-sindhu p. 73"),
        "only_day": ("The tithi touches no sunrise: its only day", "Nirnaya-sindhu p. 73"),
    },
    "shraddha": {
        "aparahna": ("The Amavasya touches the aparahna (the last third of the daytime) of one day: that day", "Nirnaya-sindhu pp. 81, 87"),
        "aparahna_both_kutapa": ("It touches both afternoons: the day whose kutapa (the 8th of the 15 day muhurtas) it covers (Madhava)", "Nirnaya-sindhu p. 87"),
        "kutapa_one_day": ("Neither afternoon: the day whose kutapa it covers", "Nirnaya-sindhu pp. 86-87"),
        "kutapa_more": ("Kutapa partly covered on both days: the day with more", "Nirnaya-sindhu p. 87"),
        "kutapa_tie_kshaya_earlier": ("Equal on both days and the Amavasya touches no sunrise: the earlier day (Pracetas)", "Nirnaya-sindhu p. 87"),
        "kutapa_tie_later": ("Equal on both days, or covered on both: the later day (Pracetas)", "Nirnaya-sindhu p. 87"),
        "kutapa_none_later": ("Neither afternoon nor kutapa touched: the later day (our fallback; not seen in practice)", None),
    },
    "pradosha": {
        "covers_pradosha": ("The day whose pradosha (three muhurtas after sunset) the Trayodashi reaches", "Nirnaya-sindhu p. 72, footnote (Brahmottara-khanda)"),
        "both_covered_later": ("The Trayodashi reaches pradosha on both days: the later day; Mayukha (after Sumantu) takes the earlier", "Nirnaya-sindhu p. 72, footnote"),
        "neither_covered_later": ("The Trayodashi reaches pradosha on neither day: the later day; Mayukha (after Sumantu) takes the earlier", "Nirnaya-sindhu p. 72, footnote"),
    },
}  # fmt: skip
SHRADDHA_NOTE = (
    "Hemadri makes the kutapa primary for households without sacred fires; Harita's rule by "
    "Vedic branch decides equal coverage (Nirnaya-sindhu pp. 82, 86-87). Kshaya and vrddhi "
    "here mean the Amavasya touches no sunrise or two (our reading)."
)
EKADASHI_NOTE = (
    "A tithi runs long when it is still current at the sunrise after its own day: Ekādaśī at "
    "the second day's sunrise, Dvādaśī at the third's, counting from the first Ekādaśī day "
    "(our reading of Nirnaya-sindhu pp. 59-62)."
)
ASPECTS = {
    "source": {
        "text": "Brihat Parasara Hora Sastra",
        "verse": "27.2-3",
        "edition": "with Devachandra Jha's Vimarsa-sudha, 1939",
        "page": "151",
    },
    "scope": (
        "Full aspects only. BPHS 27.2 also gives partial aspects (a quarter on the 3rd and "
        "10th, a half on the 5th and 9th, three quarters on the 4th and 8th), not shown here. "
        "BPHS 27, Brihat Jataka 2.13 and Jataka Parijata 2.30-31 give Rahu and Ketu no aspect."
    ),
}
# PD 6.5: "There are some who declare that there is no Kemadruma where ..."
# PD 26.22-23 (1937, pp. 293-294), quoted as printed; no predictions of our own.
SADE_SATI_PHASES = {
    "rising": (12, "When Saturn is in the 12th house, the native will be wearied by being engaged in a worthless and fruitless business. He will be robbed of his moneys by his enemies. His wife and sons will suffer from sickness.", "26.23"),
    "peak": (1, "During Saturn's transit through the Janmarasi, the native will suffer from disease; he will perform funeral rites;", "26.22"),
    "setting": (2, "in the 2nd house he will suffer trouble to wealth and children", "26.22"),
}  # fmt: skip
YOGA_CHECKS = {
    "moon_in_kendra": "The Moon is in a kendra from the lagna",
    "planet_with_moon": "A graha is with the Moon",
    "planet_in_kendra_from_moon": "A graha is in a kendra from the Moon",
}
DIGNITY_NOTES = {
    "node_debilitation_our_reading": "Debilitated as the 7th sign from its exaltation (our reading; BPHS names no sign)",
    "node_own_sign_by_some": "Own sign according to some (BPHS Dasa-phala v.36); the main view is Aquarius for Rahu, Scorpio for Ketu",
}  # fmt: skip
YOGA_CATEGORIES = {
    "mahapurusha": "Pancha Mahapurusha", "raja": "Raja yoga", "dhana": "Dhana yoga",
    "vipareeta": "Vipareeta Raja yoga", "cancellation": "Neecha Bhanga", "lunar": "Lunar yoga",
    "solar": "Solar yoga", "exchange": "Parivartana", "dosha": "Dosha",
    "auspicious": "Auspicious yoga", "nabhasa": "Nabhasa yoga",
    "modern": "Modern usage (no classical source found)",
}  # fmt: skip
YOGA_NOTES = {
    "strength_our_reading_of_bphs": "Strong read as shadbala at or above BPHS's required rupas (our reading)",
    "bphs_42_our_reading": "Our reading of BPHS 42: every named graha in the 11th, or in or aspecting the lagna",
}  # fmt: skip
SPECIAL_YOGAS = {
    "amrita_siddhi": ("Siddhi (amrta) yoga", "Narada, quoted in Muhurta Chintamani 1.21's commentary, p. 20. Avoided on its excluded tithi (1.20-21) and for its act (1.22: Tuesday-Ashwini for entering a house, Saturday-Rohini for a journey, Thursday-Pushya for a marriage); it never lifts Bhadra, Vyatipata or Vaidhriti (p. 35)"),
    "visha": ("Visha yoga", "Muhurta Chintamani 1.20-21, pp. 19-20: a siddhi pair on its excluded tithi (Daivajna-manohara calls these visha)"),
    "sarvartha_siddhi": ("Sarvartha Siddhi", "Muhurta Chintamani 1.28-29, p. 22, main reading (a footnoted variant reads Anuradha for Purva Phalguni on Friday)"),
    "siddha": ("Siddha", "Muhurta Chintamani 1.4, Kasyapa in the commentary, p. 12"),
    "marana": ("Marana (Mrtyu)", "Muhurta Chintamani 1.30, p. 23"),
    "dagdha": ("Dagdha", "Muhurta Chintamani 1.5, Narada in the commentary, p. 13"),
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
    "gaja_kesari": ("Gaja Kesari", "lunar"), "chandra_mangala": ("Chandra-Mangala", "modern"),
    "adhi": ("Adhi", "lunar"), "shakata": ("Shakata", "lunar"),
    "ubhayachari": ("Ubhayachari", "solar"), "vesi": ("Vesi", "solar"), "vasi": ("Vasi", "solar"),
    "budha_aditya": ("Budha-Aditya", "modern"),
    "dainya_parivartana": ("Dainya Parivartana", "exchange"),
    "khala_parivartana": ("Khala Parivartana", "exchange"),
    "maha_parivartana": ("Maha Parivartana", "exchange"),
    "kuja_dosha": ("Kuja (Mangal) Dosha (Khankhoje 1943)", "dosha"),
    "kala_sarpa": ("Kala Sarpa", "modern"), "amala": ("Amala", "auspicious"),
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
    "gada": ("Gada", "nabhasa"), "vajra": ("Vajra", "nabhasa"), "yava": ("Yava", "nabhasa"),
    "ardhachandra": ("Ardhachandra", "nabhasa"),
}  # fmt: skip

MUHURTA_RULE_NAMES = {
    "rahu_kalam": "Rahu Kalam", "yamaganda": "Yamaganda", "gulika": "Gulika Kalam",
    "durmuhurta": "Durmuhurta", "bad_yoga_window": "Inauspicious yoga (opening ghatis)",
    "bad_yoga_after_opening": "Inauspicious yoga, past its opening",
    "bhadra_earth": "Bhadra on earth (MC 1.45)",
    "visha_yoga": "Visha yoga: a siddhi pair on its excluded tithi (MC 1.20-21)",
    "siddhi_pair_act_ban": "Siddhi pair avoided for this act (MC 1.22)",
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
    "kharmas": "Kharmas", "amrita_siddhi": "Siddhi (amrta) yoga", "sarvartha_siddhi": "Sarvartha Siddhi",
    "lagna_lord_strong": "Lagna lord strong", "benefic_kendra": "Benefic in a kendra",
    "abhijit": "Abhijit muhurta", "movable_lagna": "Movable lagna", "fixed_lagna": "Fixed lagna",
    "favoured_hora": "Favoured hora", "malefic_hora": "Mars or Saturn hora",
}  # fmt: skip
VETOES = {
    "rahu_kalam", "yamaganda", "gulika", "durmuhurta", "bad_yoga_window", "bhadra_earth",
    "amavasya", "rikta_tithi", "ashtami", "marana_yoga", "dagdha_yoga", "moon_8th",
    "chandrashtama", "disha_shool", "visha_yoga", "siddhi_pair_act_ban",
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
    "conjunct_first_letter": "A conjunct is read by its first letter, keeping the cluster's vowel",
    "vowel_pairs": "Long and short vowels count as one, and so do e and ai, o and au",
    "equivalent_letters": "Ba and va, śa and sa, kha and ṣa stand for each other when a syllable is missing",
    "nasal_read_as": "Names in ṅa, ña and ṇa are read as ga, ja and ḍa",
    "r_vowel_as_ra": "Ṛ, which the chakra does not list, is read as ra",
    "abhijit_as_uttara_ashadha": "Abhijit's syllables count as Uttarashadha pada 4",
    "r_in_syllable_as_ra": "Our reading: ṛ after a consonant is read as ra, then the conjunct rule applies (kṛ gives ka)",
    "single_cell_consonant": "Our reading: a consonant the chakra lists only once takes that cell whatever its vowel",
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
        "windows": {
            k: {
                "name": n,
                "description": d,
                "source": WINDOW_SOURCES.get(k),
                "note": WINDOW_NOTES.get(k),
            }
            for k, (n, d) in WINDOWS.items()
        },
        "bhadraResidences": {
            k: {"name": n, "description": d, "source": "Muhurta Chintamani 1.45, p. 38"}
            for k, (n, d) in BHADRA_RESIDENCES.items()
        },
        "specialYogas": {k: {"name": n, "source": src} for k, (n, src) in SPECIAL_YOGAS.items()},
        "dignities": {k: {"name": v} for k, v in DIGNITIES.items()},
        "dignityNotes": {k: {"name": v} for k, v in DIGNITY_NOTES.items()},
        "aspects": ASPECTS,
        "ekadashiTraditions": {k: {"name": v} for k, v in EKADASHI_TRADITIONS.items()},
        "pakshas": {k: {"name": v} for k, v in PAKSHAS.items()},
        "dashaLevels": {k: {"name": v} for k, v in DASHA_LEVELS.items()},
        "ekadashiRules": {
            t: {k: {"name": n, "source": src} for k, (n, src) in rules.items()}
            for t, rules in EKADASHI_RULES.items()
        },
        "ekadashiNote": EKADASHI_NOTE,
        "observanceRules": {
            group: {k: {"name": n, "source": src} for k, (n, src) in rules.items()}
            for group, rules in OBSERVANCE_RULES.items()
        },
        "shraddhaNote": SHRADDHA_NOTE,
        # keyed by the rows' nameId: "<purnimanta month>_<paksha>", or "adhika_<paksha>"
        "ekadashiNames": {
            nid: {
                "name": name,
                "otherNames": list(others),
                "alsoPrinted": {"name": printed, "source": NS_P51} if printed else None,
                "popularName": popular,
                "source": f"{EM['text']}, {EM['edition']}, {folio}",
                "note": NAME_NOTES.get(nid),
            }
            for nid, (name, others, printed, popular, folio) in EKADASHI_NAMES.items()
        },
        "yogaCategories": {k: {"name": v} for k, v in YOGA_CATEGORIES.items()},
        "yogas": {k: {"name": n, "category": c} for k, (n, c) in YOGAS.items()},
        "yogaNotes": {k: {"name": v} for k, v in YOGA_NOTES.items()},
        "sadeSatiPhases": {
            k: {
                "saturnHouse": house,
                "quote": quote,
                "source": {
                    "text": "Phaladipika",
                    "verse": verse,
                    "edition": "Mantresvara, tr. V. Subrahmanya Sastri, 1937",
                    "page": "293",
                },
            }
            for k, (house, quote, verse) in SADE_SATI_PHASES.items()
        },
        "yogaChecks": {
            "kemadruma": {
                "name": "Some hold there is no Kemadruma when (Phaladipika 6.5, not applied):",
                "checks": {k: {"name": v} for k, v in YOGA_CHECKS.items()},
            }
        },
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
            "rules": {
                k: {"name": NAME_RULES[k], "source": src, "ourReading": k in AV.OUR_READINGS}
                for k, src in AV.RULES.items()
            },
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
