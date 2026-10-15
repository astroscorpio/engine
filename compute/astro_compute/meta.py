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
        "covers_pradosha": ("The day whose whole pradosha (three muhurtas after sunset) the Trayodashi covers", "Nirnaya-sindhu p. 72, footnote (Brahmottara-khanda)"),
        "both_covered_later": ("It covers pradosha on both days: the later day; Mayukha (after Sumantu) takes the earlier", "Nirnaya-sindhu p. 72, footnote"),
        "neither_covered_later": ("It reaches neither day's pradosha: the later day; Mayukha (after Sumantu) takes the earlier", "Nirnaya-sindhu p. 72, footnote"),
        "equal_touch_later": ("It touches both pradoshas equally: the later day; Mayukha takes the earlier", "Nirnaya-sindhu p. 72, footnote"),
        "more_pradosha": ("It covers part of pradosha, on one evening only or unequally on both: the day with more of it (the other opinion recorded there)", "Nirnaya-sindhu p. 72, footnote"),
    },
}  # fmt: skip
# observances.md s9 (provisional: the lead's decision 3)
OBSERVANCE_RULES["parana"] = {
    "morning": (
        "Within the first three muhurtas after sunrise, once Hari-vasara (Dvadashi's first quarter) is over and before Dvadashi ends (the majority)",
        "Dharmasindhu p. 19; Nirnaya-sindhu p. 71",
    ),
    "afternoon": (
        "Hari-vasara outlasts the first three muhurtas: the afternoon (the 4th fifth of the day) within Dvadashi, never at midday (some)",
        "Dharmasindhu p. 19",
    ),
    "trayodashi": (
        "No Dvadashi is left at sunrise: on Trayodashi, in the first three muhurtas",
        "Dharmasindhu p. 19",
    ),
    "within_dvadashi": ("After Hari-vasara and before Dvadashi ends (our fallback)", None),
}
PARANA_NOTE = (
    "Break the fast before Dvadashi ends (breakBefore): letting Dvadashi pass is a grave fault "
    "(Dharmasindhu p. 19). In a difficulty, water counts as breaking it (Devala, Nirnaya-sindhu "
    "p. 71). With a short Dvadashi the morning and midday rites move to dawn so the meal falls "
    "inside it (NS p. 70). Nirnaya-sindhu's own teachers prefer the afternoon even when the "
    "morning is open (p. 71)."
)
# observances.md s8 (provisional: the lead's decision 8)
OBSERVANCE_RULES["mahalaya"] = {
    "one_day": (
        "The tithi holds the afternoon (the 10th-12th day muhurtas, our reading) of one day only: that day",
        "Nirnaya-sindhu p. 718",
    ),
    "both_earlier": (
        "It holds both afternoons, fully or equally in part: the earlier day",
        "Nirnaya-sindhu p. 718",
    ),
    "more": (
        "It holds part of both afternoons, unequally: the day with more (Marici)",
        "Nirnaya-sindhu p. 718",
    ),
    "neither_three_muhurtas_earlier": (
        "Neither afternoon, but current three muhurtas before the first day's sunset: the earlier day (Sumantu)",
        "Nirnaya-sindhu p. 719",
    ),
    "neither_later": (
        "Neither afternoon: the later day, whose kutapa it holds (Gobhila)",
        "Nirnaya-sindhu p. 719",
    ),
}
OBSERVANCE_RULES["ekoddishta"] = {
    "one_day": (
        "The Chaturdashi holds the midday (kutapa to rauhina, the 8th-9th day muhurtas) of one day only: that day",
        "Nirnaya-sindhu p. 718",
    ),
    "both_earlier": (
        "Both middays, fully or equally in part: the earlier day",
        "Nirnaya-sindhu p. 718",
    ),
    "more": ("Both, unequally: the day with more", "Nirnaya-sindhu p. 718"),
    "neither_earlier": (
        "Neither midday: the earlier day; the Gauda later-day view is rejected",
        "Nirnaya-sindhu p. 718",
    ),
}
OBSERVANCE_RULES["matamaha"] = {
    "one_day": (
        "The Pratipada current at sangava (the 4th-6th day muhurtas, our reading) of one day only: that day",
        "Nirnaya-sindhu p. 239 (Nirnaya-dipa)",
    ),
    "both_earlier": ("At both sangavas, fully or equally: the earlier day (our reading)", None),
    "more": ("At both, unequally: the day with more (our reading)", None),
    "neither_later": ("At neither: the later day (our fallback)", None),
}
PITRU_PAKSHA_NOTES = {
    "fortnight": "The dark fortnight ending amanta Bhadrapada (purnimanta Ashvina), the fifth from the Ashadha full moon; NS counts its sixteen days to Ashvina shukla Pratipada (p. 215). Each tithi's day is for those who died on that tithi.",
    "windows": "Day muhurtas are fifteenths of sunrise to sunset. The afternoon is the 10th-12th (the fourth fifth of the day: our reading, from NS p. 717's five-part midday); kutapa to rauhina the 8th-9th (Gautama, p. 718); sangava the 4th-6th (our reading).",
    "navami": "Navami: for all mothers, stepmothers too, even by a son whose father lives (NS p. 229). Popularly 'Avidhava Navami': NS feeds a suvasini with the brahmanas for a woman who died before her husband (p. 231) but does not limit the day to such women, and the name was not found.",
    "dvadashi": "Dvadashi: for renunciants (Vayu Purana via the Prthvicandrodaya, NS p. 232).",
    "trayodashi": "Trayodashi: dear to the ancestors, more so with Magha (Candrika, NS p. 232); obligatory, kept even in an intercalary month (pp. 233-234). A man with children offers no pindas on a Magha-joined Trayodashi (Brhat-Parasara, p. 234). With the Moon in Magha and the Sun in Hasta it is gaja-cchaya (p. 233).",
    "chaturdashi": "Chaturdashi: only for those killed by weapons, falls, lightning, water, poison, fire or animals, not for deaths in childbirth (NS p. 235). It is an ekoddishta (p. 236), so the midday decides; variantDate is the afternoon table's day where it differs.",
    "amavasya": "Amavasya: the last day of the fortnight. With the Moon and the Sun both in Hasta it is also gaja-cchaya (Yama via Apararka, NS p. 238). 'Sarva-pitr' was not found as a name.",
    "bharani": "Bharani in the pitr-paksha is 'great': a shraddha then equals one at Gaya (Matsya via the Prthvicandrodaya, NS p. 225); popularly Maha-bharani. The texts read do not fix the hour; the day whose afternoon holds the star is shown.",
    "magha": "Magha is a shraddha occasion of its own (Vasishtha, Yajnavalkya; NS p. 233). The day whose afternoon holds the star is shown.",
    "matamaha": "Ashvina shukla Pratipada: the maternal grandfather's shraddha by a daughter's son, even newborn (Hemadri's Sangraha, NS p. 239). The Nirnaya-dipa takes the Pratipada current at sangava, a verse whose source NS doubts. Not in an intercalary month.",
    "purnima": "Some almanacs list a Purnima shraddha on the Bhadrapada full moon; the texts read give it no day, so none is shown.",
    "variant": "Madhava and the Prthvicandrodaya take the earlier day in kshaya and the later in vrddhi, of the following tithi, when the afternoon is covered on both days (NS pp. 719-720). Not computed: the comparison it rests on is not defined on the pages read.",
}  # fmt: skip
OBSERVANCE_RULES["sankashti"] = {
    "moonrise": ("The krishna Chaturthi current at moonrise", "Nirnaya-sindhu p. 47; Viramitrodaya, Samaya-prakasha, p. 38"),
    "both_earlier": ("Current at both moonrises: the earlier day, joined with Trtiya (some, in NS); others take the later day", "Nirnaya-sindhu p. 47"),
    "neither_later": ("Current at neither moonrise: the later day", "Nirnaya-sindhu p. 47"),
}  # fmt: skip
FESTIVAL_RULES = {
    "dipavali": {
        "pradosha": ("The Amavasya current at pradosha", "Nirnaya-sindhu pp. 299-300"),
        "danda_next_night_later": ("It touches at least one danda (24 minutes) of the next night: the later day (Tithi-tattva)", "Nirnaya-sindhu p. 300"),
        "neither_later": ("Current at neither pradosha: the later day (our fallback)", None),
    },
    "shivaratri": {
        "midnight_both_pradosha_later": ("Midnight on both days, pradosha only on the later: the later day (Madhava, endorsed by NS); Hemadri takes the first", "Nirnaya-sindhu p. 336"),
        "midnight_both_pradosha": ("Midnight on both days, pradosha only on the first: the first day", "Nirnaya-sindhu p. 337"),
        "midnight_both_first": ("Midnight on both days, pradosha on both or neither: the first day (Hemadri)", "Nirnaya-sindhu p. 335"),
        "by_midnight": ("Midnight decides: the day with (more of) it, so the first when it has all of midnight (Isana-samhita)", "Nirnaya-sindhu pp. 336-337"),
        "by_pradosha": ("No midnight on either day: the day with pradosha", "Nirnaya-sindhu p. 337"),
        "neither_later": ("Neither window on either day: the later day (our fallback)", None),
    },
    "ganesha-chaturthi": {
        "next_day_midday": ("The Chaturthi reaches the next day's midday: the next day", "Nirnaya-sindhu pp. 47, 198 (Brhaspati)"),
        "trtiya_joined_earlier": ("Otherwise the earlier day, joined with Trtiya", "Nirnaya-sindhu pp. 47, 198"),
    },
    "raksha-bandhan": {
        "udaya_three_muhurtas": ("The Purnima lasts more than three muhurtas after the later sunrise: that day, in the afternoon or at pradosha, free of Bhadra", "Dharmasindhu p. 49"),
        "earlier_pradosha": ("Otherwise the earlier day, at pradosha or about then, free of Bhadra", "Dharmasindhu p. 49"),
    },
    "janmashtami": {
        "first_only": ("The Ashtami at midnight on the first day only: the first", "Nirnaya-sindhu pp. 189-190"),
        "second_only": ("At midnight on the second day only: the second", "Nirnaya-sindhu pp. 189-190"),
        "both_later": ("At midnight on both days, equally: the second; the Ashtami joined with Saptami is avoided (Brahma-vaivarta)", "Nirnaya-sindhu p. 190"),
        "neither_later": ("At midnight on neither day: the second", "Nirnaya-sindhu p. 190"),
        "more": ("Partly on both days, unequally: the day with more of it", "Nirnaya-sindhu p. 190"),
        "split_rohini_day": ("The Ashtami holds the first midnight and meets Rohini on the second day: one observance, on the Rohini day (Madhava). Nirnaya-sindhu keeps two fasts, the first day being its Janmashtami (variantDate); Hemadri keeps the first", "Dharmasindhu pp. 50-51; Nirnaya-sindhu pp. 191-192"),
    },
    "jayanti": {
        "first": ("The Ashtami and Rohini together at midnight on the first day only: the first, even when joined with Saptami (Padma)", "Nirnaya-sindhu p. 190"),
        "second": ("Together at midnight on the second day only: the second", "Nirnaya-sindhu p. 190"),
        "both_later": ("Together at midnight on both days: the second (Brahma-vaivarta)", "Nirnaya-sindhu pp. 190-191"),
        "split_later": ("The Ashtami at the first midnight, Rohini at the second: the second, for the Jayanti joining (Madhava); Hemadri takes the first", "Nirnaya-sindhu p. 191"),
    },
    "sharad-navaratri": {
        "pratipada_at_sunrise": ("The Pratipada current at sunrise, best lasting three muhurtas after it, then two, by some texts one; never the one joined with Amavasya", "Dharmasindhu p. 65; Nirnaya-sindhu pp. 240-241"),
        "full_day_first": ("The Pratipada fills a whole day and runs into the next: the first, as complete", "Dharmasindhu p. 65"),
        "under_one_muhurta_amavasya_joined": ("The Pratipada lasts under a muhurta after sunrise: the day joined with Amavasya", "Dharmasindhu p. 65"),
        "no_sunrise_amavasya_joined": ("The Pratipada touches no sunrise: its only day, joined with Amavasya", "Dharmasindhu p. 65"),
    },
    "vijayadashami": {
        "aparahna": ("The Dashami in the afternoon of one day only: that day", "Nirnaya-sindhu p. 284"),
        "aparahna_both_earlier": ("In the afternoon of both days, covering or touching it: the earlier", "Nirnaya-sindhu p. 284"),
        "shravana_later": ("In the afternoon of both days, with Shravana in the later day's afternoon: the later", "Nirnaya-sindhu pp. 283-284; Dharmasindhu p. 71"),
        "pradosha_both_later": ("Pradosha on both days, the afternoon only on the later: the later", "Nirnaya-sindhu p. 284"),
        "pradosha": ("No afternoon on either day: the day with pradosha, the secondary time", "Nirnaya-sindhu p. 284"),
        "neither_later": ("Neither window on either day: the later day (our fallback)", None),
    },
    "holika-dahana": {
        "pradosha_later": ("Pradosha on both days, or partly on the second: the second, since Bhadra falls on the first", "Dharmasindhu p. 94; Nirnaya-sindhu p. 342"),
        "pradosha": ("The Purnima at the first day's pradosha, free of Bhadra (Narada)", "Dharmasindhu p. 94; Nirnaya-sindhu p. 342"),
        "sardha_triyama_later": ("The first pradosha in Bhadra; the Purnima lasts 3 1/2 yamas into the second day and the Pratipada grows: the second day's pradosha, in Pratipada (Bhavishya)", "Dharmasindhu p. 94; Nirnaya-sindhu p. 343"),
        "shrinking_pratipada_tail": ("As above but the Pratipada shrinks: the first night, in Bhadra's tail or in Bhadra avoiding its face", "Dharmasindhu p. 94"),
        "after_bhadra_before_midnight": ("The first pradosha in Bhadra, which ends before midnight: once it ends, before midnight (the midnight limit is our reading)", "Dharmasindhu p. 94"),
        "bhadra_avoiding_face": ("Bhadra ends after midnight: at pradosha in Bhadra, avoiding only its face (the others in Nirnaya-sindhu; 'the practice of the learned')", "Dharmasindhu p. 94; Nirnaya-sindhu pp. 343-344"),
        "neither_tail": ("Pradosha on neither day: the first night, in Bhadra's tail", "Dharmasindhu p. 94"),
        "neither_after_pradosha": ("Pradosha on neither day and no tail at night: in Bhadra after pradosha, avoiding its face (a first-half Bhadra is allowed at night, MC 1.44)", "Dharmasindhu p. 94"),
    },
}  # fmt: skip
FESTIVAL_NOTES = {
    "dipavali": "Lakshmi is worshipped at pradosha on this day (Bhavishya, NS p. 299). Divodasiya prefers an Amavasya covering both pradosha and midnight (NS p. 300); nishithaCovered says whether it does. No fixed-lagna (Vrishabha) muhurat is sourced.",
    "mahashivaratri": "The dark Chaturdashi ending amanta Magha (purnimanta Phalguna). Some texts take pradosha, others midnight (NS p. 334). A Chaturdashi joined with Amavasya is avoided (Skanda, p. 337).",
    "masik-shivaratri": "Every dark Chaturdashi, by the same tests (NS p. 340). Hemadri keeps the name for the Magha one only and takes the day with more of the night, the earlier when equal.",
    "ganesha-chaturthi": "Worship at midday (pujaWindow, the 3rd fifth of the daytime, NS p. 28). Do not look at the Moon while the Chaturthi runs (moonAvoid; Markandeya in NS p. 198); a Moon that rose in Chaturthi may be seen once Panchami begins.",
    "raksha-bandhan": "The Shravana Purnima. Dharmasindhu p. 49 sets the day by how long the Purnima lasts after the later sunrise; tieWindow is that day's afternoon (the 4th fifth of the daytime, our reading) or pradosha, free of Bhadra. Nirnaya-sindhu p. 180 keeps the earlier day's afternoon, after Bhadra even at night, and never the Purnima joined with Pratipada; its day is variantDate where it differs. bhadra is the Vishti karana, the Purnima's first half. It is kept on eclipse and sankranti days too.",
    "janmashtami": "The dark Ashtami ending amanta Shravana (purnimanta Bhadrapada). Midnight decides (NS p. 189). Jayanti is the Ashtami joined with Rohini; NS holds both vratas due, though people keep only Janmashtami (p. 187). In a split year the date is the Rohini day (Madhava, Dharmasindhu pp. 50-51) and variantDate is Nirnaya-sindhu's first-day fast (it keeps both, p. 192). udayaDate is the sunrise view, which Vaishnava calendars follow; NS sets it aside as baseless (p. 191).",
    "sharad-navaratri": "Kalasha-sthapana on Ashvina shukla Pratipada. sthapanaWindow is the first ten ghatikas (four hours) after sunrise while the Pratipada runs, failing that the Abhijit muhurta; never in the afternoon or at night (Dharmasindhu pp. 65-66). muhurtasAfterSunrise is how long the Pratipada lasts after that sunrise. cautions lists the Pratipada's first sixteen nadis, Chitra and Vaidhriti where they touch the window: avoided where the time allows, never at the cost of the forenoon (DS p. 65).",
    "vijayadashami": "Ashvina shukla Dashami. pujaWindow is the afternoon (the 4th fifth of the daytime, our reading) while the Dashami runs. Aparajita puja is done in the afternoon facing north-east (Skanda via Hemadri, NS p. 283). The Vijaya moment is just after twilight as the first stars appear (Narada, p. 284); not computed.",
    "holika-dahana": "The Phalguna Purnima, lit at night, never by day (Dharmasindhu p. 94). Bhadra's tail is the last 3 ghatikas of the tithi's 3rd prahara and its face the first 5 of the 4th (DS pp. 94-95, MC 1.44); the tail is auspicious, the face never used. Nirnaya-sindhu is stricter, lighting only after Bhadra ends (p. 343); its day is variantDate where it differs. Not in an adhika month (NS p. 344).",
}  # fmt: skip
# panchang-yogas.md s1
BHADRA_PARTS = {
    "face": {
        "name": "Bhadra's face",
        "note": "The first 5 ghatis of one prahara (an eighth of the tithi), by tithi; bad.",
        "source": "Muhurta Chintamani 1.44, pp. 35-36",
    },
    "tail": {
        "name": "Bhadra's tail",
        "note": "The last 3 ghatis of another prahara; auspicious.",
        "source": "Muhurta Chintamani 1.44, pp. 35-36",
    },
    "dayNight": "MC 1.44 adds that a Bhadra in the second half of a tithi is auspicious by day, and one in the first half at night. The avoid list does not apply this yet.",
}
FESTIVAL_CAUTIONS = {
    "first_16_nadis": "The Pratipada's first sixteen nadis (6 h 24 min)",
    "chitra": "The Moon in Chitra",
    "vaidhriti": "Vaidhriti yoga",
}
SANKASHTI_NOTE = (
    "Krishna paksha, by common practice; the texts read do not state the fortnight. Moonrise "
    "is the visible rise, the Moon's upper limb with refraction (our convention; the texts "
    "do not say). On a Tuesday it is popularly Angaraki: a Chaturthi on a Tuesday 'gives "
    "fruit like the equinox' (Satatapa, Nirnaya-sindhu p. 73); the name was not found in the "
    "pages read."
)
# methodology.md e
HORA_SYSTEMS = {
    "seasonal": {
        "name": "Seasonal horas: the daytime and the night each in 12 parts",
        "source": None,
        "note": "As computed; no printed source is cited for the day/12 and night/12 split.",
    },
    "equal": {
        "name": "Equal horas: 60 minutes (2.5 ghatis) each from sunrise",
        "source": "Muhurta Chintamani 1.55, p. 49 (commentary, quoting Vivaha-vrndavana)",
        "note": "MC counts the horas from the start of the weekday; Vivaha-vrndavana from sunrise, which is used here. The 24th runs to the next sunrise.",
    },
}
PURNIMA_EARLIER_NOTE = (
    "Some almanacs list a Purnima vrat on this earlier day; popular practice, source pending."
)
# observances.md s6
AMAVASYA_NAMES = {
    "mahalaya": ("Mahalaya Amavasya", "The last day of the Mahalaya fortnight, the dark fortnight after the Bhadrapada full moon", "Nirnaya-sindhu p. 215"),
    "magha": ("Magha Amavasya", "A yugadi day: the new moon that ends amanta Magha", "Nirnaya-sindhu p. 341"),
    "mauni": ("Mauni Amavasya (popular name)", "The new moon inside purnimanta Magha (amanta Pausha); the texts read do not use the name. Nirnaya-sindhu asks for silence during the Magha bath, which this new moon falls inside", "Nirnaya-sindhu p. 324 (silence in the Magha bath)"),
    "somavati": ("Somavati Amavasya (Monday)", "A Monday Amavasya 'gives fruit like the equinox'; the commentary says 'somavari amavas'", "Nirnaya-sindhu p. 73 (Satatapa, Vyasa)"),
    "bhauma": ("Bhauma Amavasya (Tuesday)", "On a Tuesday Amavasya, bathing in the Ganga gives the fruit of a thousand cows", "Nirnaya-sindhu p. 73 (Satatapa)"),
    "shani": ("Shani Amavasya (Saturday)", "Popular observance; no classical source found", None),
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
# PD 26.22-23 (1937, pp. 294-295), quoted as printed; no predictions of our own.
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
    "amrita_siddhi": ("Siddhi (amrta) yoga", "Narada, quoted in Muhurta Chintamani 1.21's commentary, p. 20. Avoided on its excluded tithi (1.20-21) and for its act (1.22: Tuesday-Ashwini for entering a house, Saturday-Rohini for a journey, Thursday-Pushya for a marriage); it never lifts Bhadra, Vyatipata or Vaidhriti (p. 35)", "good"),
    "visha": ("Visha yoga", "Muhurta Chintamani 1.20-21, pp. 19-20: a siddhi pair on its excluded tithi (Daivajna-manohara calls these visha)", "avoid"),
    "sarvartha_siddhi": ("Sarvartha Siddhi", "Muhurta Chintamani 1.28-29, p. 22, main reading (a footnoted variant reads Anuradha for Purva Phalguni on Friday)", "good"),
    "siddha": ("Siddha", "Muhurta Chintamani 1.4, Kasyapa in the commentary, p. 12", "good"),
    "marana": ("Marana (Mrtyu)", "Muhurta Chintamani 1.30, p. 23", "avoid"),
    "utpata": ("Utpata", "Muhurta Chintamani 1.30, p. 23: the first of each weekday's run of four nakshatras; 'its effect is like its name'", "avoid"),
    "kana": ("Kana", "Muhurta Chintamani 1.30, p. 23: the third of the run. Monday's is Abhijit, the last quarter of Uttara Ashadha and the first fifteenth of Shravana (Muhurta-martanda 1909, p. 139)", "avoid"),
    "siddhi": ("Siddhi (weekday and nakshatra)", "Muhurta Chintamani 1.30, p. 23: the fourth of the run; 'its effect is like its name'", "good"),
    "mahapata": ("Mahapata (equal declinations)", "Muhurta Chintamani 1.34, commentary p. 30: the moment the Sun's and Moon's declinations are equal, computed by the Surya-siddhanta 11 (Burgess): Vyatipata-type with longitudes summing to about 180 degrees and declinations equal, Vaidhriti-type summing to about 360 and opposite; its half-duration is per Surya-siddhanta 11.14, sixty times the half-sum of the two discs over the difference of the daily motions, in nadis; near the equator it can occur twice, near a solstice not at all (11.19). Narada, quoted in MC, avoids the whole day", "avoid"),
    "ravi": ("Ravi yoga", "Muhurta Chintamani 1.27, p. 22: the Moon's nakshatra the 4th, 6th, 9th, 10th, 13th or 20th from the Sun's, counted inclusively (our reading); it 'destroys a host of defects'", "good"),
    "dagdha": ("Dagdha", "Muhurta Chintamani 1.5, Narada in the commentary, p. 13", "avoid"),
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
        "bhadraParts": BHADRA_PARTS,
        "bhadraResidences": {
            k: {"name": n, "description": d, "source": "Muhurta Chintamani 1.45, p. 38"}
            for k, (n, d) in BHADRA_RESIDENCES.items()
        },
        "specialYogas": {
            k: {"name": n, "source": src, "quality": quality}
            for k, (n, src, quality) in SPECIAL_YOGAS.items()
        },
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
        "sankashtiNote": SANKASHTI_NOTE,
        "paranaNote": PARANA_NOTE,
        "pitruPakshaNotes": PITRU_PAKSHA_NOTES,
        "horaSystems": HORA_SYSTEMS,
        "festivalRules": {
            group: {k: {"name": n, "source": src} for k, (n, src) in rules.items()}
            for group, rules in FESTIVAL_RULES.items()
        },
        "festivalNotes": FESTIVAL_NOTES,
        "festivalCautions": FESTIVAL_CAUTIONS,
        "purnimaEarlierDateNote": PURNIMA_EARLIER_NOTE,
        "amavasyaNames": {
            k: {"name": n, "note": note, "source": src}
            for k, (n, note, src) in AMAVASYA_NAMES.items()
        },
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
