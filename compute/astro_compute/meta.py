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
from jyotisha.vargas import VARGA_NAMES

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
    "brahma": "Current practice: the 14th of the night's 15 muhurtas, ending one muhurta before sunrise. Manusmriti 4.92 names the brahma muhurta; Kulluka (1909, p. 149) reads it as the last yama of the night, and Govindaraja, as Kulluka reports him, as its last muhurta.",
}
# gochara.md: what the gochara endpoint leaves to notes (the lead's rulings, 15 Oct 2026).
GOCHARA_NOTES = {
    "count": "Houses are counted from the Moon sign, which is the 1st (Phaladipika 26.1).",
    "exemptions": "The Sun and Saturn never block each other, nor do the Moon and Mercury (PD 26.3-6; MC 4.4a). The nodes neither have nor cause vedha (blocking by the seven grahas only is our reading).",
    "nodes": "Rahu and Ketu follow PD 26.2, like the Sun. Muhurta Chintamani 4.1 treats them like Saturn instead: good in 3, 6 and 11, with Saturn's vedha (12, 9, 5).",
    "reverseVedha": "MC 4.4-5 also make a planet in a bad house good when another occupies its paired good house (vama-vedha), counted three ways by Narada, Kasyapa and the commentator. Not computed.",
    "brightMoon": "In the bright fortnight MC 4.4 also counts the Moon good in the 2nd, 5th and 9th unless blocked from the 6th, 8th and 4th (Narada). Not computed; PD's lines for those houses are bad.",
    "timing": "Transits are classed by the sign occupied. PD 26.25: Mars and the Sun act in a sign's first third, Jupiter and Venus in the middle, the Moon and Saturn in the last, Mercury and Rahu throughout. MC 4.17's commentary has planets give the coming sign's results early (the Sun 5 days, Saturn 6 months). Neither is computed.",
    "neutralised": "Narada (MC p. 144): a planet debilitated, in an enemy's sign or combust gives neither good nor bad transit results. Not computed.",
    "regional": "Kasyapa (MC p. 144) holds that vedha applies only between the Himalaya and the Vindhya.",
    "wording": "The lines are classical statements from the 1937 translation, quoted with their verses; some speak of death or danger to life. They are not forecasts.",
}  # fmt: skip
# vivah.md (the lead's decisions of 15 Oct 2026): rule ids for /muhurat/vivah.
VIVAH_RULES = {
    "season_best": ("Magha, Phalguna, Vaishakha or Jyeshtha (amanta): best", "Muhurta Chintamani 6.13 commentary, p. 235 (Narada); Dharmasindhu p. 181"),
    "season_middling": ("Ashadha shukla 1-10, Kartika from shukla 11, or Margashirsha: middling", "Muhurta Chintamani 6.13 commentary, p. 235; 5.26, p. 186"),
    "chaturmas": ("Hari's sleep, Ashadha shukla 11 to Kartika shukla 11: barred", "Muhurta Chintamani 6.13 commentary, p. 235"),
    "sun_sign": ("The Sun in Pisces, Sagittarius or Leo: barred", "Garga in Muhurta Chintamani 6.13 commentary, p. 235"),
    "adhika_month": ("An adhika or kshaya month, and the adhika months around a kshaya month: barred", "Muhurta Chintamani 1.47, pp. 39-40; Dharmasindhu p. 4"),
    "jupiter_set": ("Jupiter within 11 time-degrees of the Sun: set", "Surya-siddhanta 9.6-7; Muhurta Chintamani 1.46-48, 5.26"),
    "jupiter_old": ("The 15 days before Jupiter sets", "Muhurta Chintamani 5.27"),
    "jupiter_infant": ("The 15 days after Jupiter rises", "Muhurta Chintamani 5.27"),
    "venus_set": ("Venus within 8 time-degrees of the Sun (retrograde) or 10 (direct): set", "Surya-siddhanta 9.6-7; Muhurta Chintamani 1.46-47, 5.26"),
    "venus_old": ("The 15 days before Venus sets in the east, or the 5 before it sets in the west", "Muhurta Chintamani 5.27"),
    "venus_infant": ("The 3 days after Venus rises in the east, or the 10 after it rises in the west", "Muhurta Chintamani 5.27"),
    "jupiter_sign": ("Jupiter in Leo or Capricorn: barred for its whole stay", "Muhurta Chintamani 1.48, p. 40"),
    "tuesday": ("Tuesday: always avoided", "Vasishtha in Muhurta Chintamani 6.53"),
    "nakshatra": ("The Moon in Mrgashira, Hasta, Mula, Anuradha, Magha, Rohini, Revati, the three Uttaras or Svati", "Muhurta Chintamani 6.53, p. 275; Dharmasindhu p. 181"),
    "vedha": ("Not pierced: a malefic anywhere in the paired star bars the whole star, a benefic only the Moon's paired quarter (1-4, 2-3)", "Muhurta Chintamani 6.54, p. 276"),
    "tithi": ("Not a rikta tithi (4, 9, 14) or Amavasya", "Muhurta Chintamani 6.53, p. 275"),
    "bhadra": ("Bhadra on earth removed from the window", "Muhurta Chintamani 1.43-45; Dharmasindhu p. 181"),
    "bad_yoga": ("The bad yogas' opening ghatis, Parigha's first half, and Vyatipata and Vaidhriti whole, removed", "Muhurta Chintamani 1.34-35; Dharmasindhu p. 181"),
    "gandanta_tithi": ("One ghatika either side of the ends of the 5th, 10th and 15th tithis, removed", "Muhurta Chintamani 6.41, p. 265"),
    "gandanta_nakshatra": ("Two ghatikas either side of Ashlesha-Magha, Jyeshtha-Mula and Revati-Ashvini, removed", "Muhurta Chintamani 6.41, p. 265"),
    "sankranti": ("16.5 ghatikas either side of the Sun's sign change, removed (half of MC's 33 each side, our reading)", "Muhurta Chintamani 6.78, p. 293"),
    "mahapata": ("Mahapata, equal declinations of the Sun and Moon, removed", "Muhurta Chintamani 6.59"),
    "eclipse": ("Days after and before an eclipse visible here: 3 and 1.5 for a quarter of the disc, 4 and 2 for half, 6 and 3 for three quarters, 8 and 4 for total (bins ours)", "Dharmasindhu p. 181, note"),
    "solar_month": ("Excluded: the lunar month is not one of the season's, though the Sun's sign is (the solar-month count MC's commentary sets aside)", "Muhurta Chintamani 6.13 commentary, p. 235"),
    "rikta": ("Excluded: a rikta tithi (Chaturthi, Navami, Chaturdashi)", "Muhurta Chintamani 6.53, p. 275"),
    "vedha_slow": ("Excluded: pierced only by a slow planet (Jupiter, Saturn, Rahu, Ketu) sitting in the paired star", "Muhurta Chintamani 6.54, p. 276"),
    "infancy_old": ("Excluded: Jupiter's or Venus's infancy or old age beyond 3 days", "Muhurta Chintamani 5.27 (5.28 gives 3 as the shortest)"),
    "utpata": ("Utpata yoga, the weekday's star in MC 1.30's utpata column (28 nakshatras), removed", "Muhurta Chintamani 1.30, p. 23"),
    "marana": ("Mrtyu yoga, the weekday's star in MC 1.30's mrtyu column, removed", "Muhurta Chintamani 1.30, p. 23"),
    "kana": ("Kana yoga, the weekday's star in MC 1.30's kana column (Monday's is Abhijit), removed", "Muhurta Chintamani 1.30, p. 23"),
    "dagdha": ("Dagdha yoga, Narada's burnt weekday-star pairs, removed", "Narada in Muhurta Chintamani 1.5 commentary, p. 13"),
    "visha": ("A siddhi (amrta) weekday-star pair on its tithi, which turns it to visha, removed", "Muhurta Chintamani 1.20-21, pp. 19-20"),
    "godhuli": ("Godhuli, the alternative: half a ghatika either side of sunset; Thursday only before it, Saturday only after; none with the Moon 1st, 6th or 8th from the lagna, or Mars 1st, 7th or 8th", "Muhurta Chintamani 6.97-99, pp. 305-307"),
    "weak_tithi": ("Shashthi or Ashtami: 'little fruit' (DS); Vasishtha drops them", "Dharmasindhu p. 181; Muhurta Chintamani 6.53"),
    "middling_weekday": ("Sunday or Saturday: middling", "Vasishtha in Muhurta Chintamani 6.53; Dharmasindhu p. 181"),
    "middling_weekday_dvadashi_trayodashi": ("Sunday or Saturday on a Dvadashi or Trayodashi: especially bad", "Vasishtha in Muhurta Chintamani 6.53"),
    "krishna_paksha": ("The dark fortnight: middling", "Dharmasindhu p. 181"),
}  # fmt: skip
VIVAH_NOTES = {
    "infancy": "Infancy and old age follow MC 5.27 by the side of the sky. MC 5.28 gives 10, 7 or 3 days as alternatives, and Dharmasindhu p. 5 takes 7 days either side as the middle view.",
    "setting": "Set means within the Surya-siddhanta 9.6-7 distance in time-degrees, measured here from the difference between the planet's and the Sun's rising (a morning planet) or setting (an evening one).",
    "jupiterLeo": "Dharmasindhu p. 5 relaxes Jupiter in Leo by region: barred everywhere only in Magha or the Leo portion; after it, no fault south of the Godavari or north of the Ganga, but between the two rivers marriage stays barred for the whole stay. Not applied.",
    "solarMonths": "The solar-month school also allows Kartika with the Sun in Scorpio, Pausha with the Sun in Capricorn and Caitra with the Sun in Aries; MC's commentator sets it aside except for a marriage that cannot wait, and Dharmasindhu allows it by local custom. Not applied.",
    "moreStars": "Haradatta adds Citra, Shravana, Dhanishtha and Ashvini (Dharmasindhu p. 181). Not applied.",
    "phase2": "The lagna (MC 6.84-85), jamitra, kartari, the navamsha rules, the other doshas of MC 6 and the couple's own charts are not applied yet.",
}  # fmt: skip
# vargas.md (the lead's decision of 15 Oct 2026): what BPHS 7.1-6 reads each varga for,
# and the six modern readings kept, labelled and uncited.
BPHS_1939 = {
    "text": "Brhat-Parashara-hora-shastra",
    "edition": "with Devachandra Jha's Vimarsha-sudha, 1939",
    "page": "57",
}
VARGA_USES = {
    1: ("The body.", "7.1", None),
    2: ("Wealth and possessions.", "7.1", None),
    3: ("Happiness from siblings.", "7.2", "courage"),
    4: ("Fortune.", "7.2", "property and home"),
    7: ("Children and grandchildren.", "7.2", None),
    9: ("The spouse.", "7.3", None),
    10: ("Great results in life.", "7.3", "career"),
    12: ("The parents.", "7.3", None),
    16: ("Comforts and vehicles.", "7.3-4", None),
    20: ("Worship and devotion.", "7.4", None),
    24: ("Learning.", "7.5", None),
    27: ("Strengths and weaknesses.", "7.5", None),
    30: ("Misfortunes.", "7.5", None),
    40: ("Good and bad results.", "7.5", "maternal legacy"),
    45: ("All matters.", "7.6", "paternal legacy"),
    60: ("All matters.", "7.6", "past karma"),
}
# griha-pravesh.md (the lead's decisions of 15 Oct 2026): rule ids for /muhurat/griha-pravesh.
GRIHA_PRAVESH_RULES = {
    "month": ("Magha, Phalguna, Vaishakha or Jyeshtha (amanta), with the Sun in its northern course", "Muhurta Chintamani 13.1, p. 437; Narada, p. 438"),
    "adhika_month": ("An adhika or kshaya month: barred", "Muhurta Chintamani 1.47, pp. 39-40; Dharmasindhu p. 4"),
    "dakshinayana": ("The Sun in its southern course, Cancer to Sagittarius: barred", "Muhurta Chintamani 13.1, p. 437"),
    "sun_sign": ("The Sun in Cancer, Virgo or Aquarius: barred", "Guru in Muhurta Chintamani 13.1 commentary, p. 439"),
    "jupiter_set": ("Jupiter within 11 time-degrees of the Sun: set", "Surya-siddhanta 9.6-7; Muhurta Chintamani 1.46, applied by the 13.1 commentary, p. 438"),
    "jupiter_old": ("The 15 days before Jupiter sets", "Muhurta Chintamani 5.27"),
    "jupiter_infant": ("The 15 days after Jupiter rises", "Muhurta Chintamani 5.27"),
    "venus_set": ("Venus within 8 time-degrees of the Sun (retrograde) or 10 (direct): set", "Surya-siddhanta 9.6-7; Muhurta Chintamani 1.46, applied by the 13.1 commentary, p. 438"),
    "venus_old": ("The 15 days before Venus sets in the east, or the 5 before it sets in the west", "Muhurta Chintamani 5.27"),
    "venus_infant": ("The 3 days after Venus rises in the east, or the 10 after it rises in the west", "Muhurta Chintamani 5.27"),
    "jupiter_sign": ("Jupiter in Leo or Capricorn: barred for its whole stay", "Muhurta Chintamani 1.48, p. 40; 13.2, 1925 printing p. 440"),
    "nakshatra": ("The Moon in Citra, the three Uttaras, Rohini, Mrgashira, Anuradha, Dhanishtha, Revati or Shatabhisha", "Vasishtha in Muhurta Chintamani 13.1 commentary, p. 439"),
    "pot_chakra": ("The pot chakra: counting the Sun's star as the 1st, the Moon's star is not 1-5 or 14-21", "Muhurta Chintamani 13.6, p. 446; Dharmasindhu p. 242"),
    "tithi": ("Not a rikta tithi (4, 9, 14) or Amavasya", "Muhurta Chintamani 13.4, p. 442"),
    "weekday": ("Not a Sunday or Tuesday", "Muhurta Chintamani 13.4, p. 442"),
    "lagna": ("A fixed lagna, or a dual one; never a movable one", "Muhurta Chintamani 13.1, 13.4; Vasishtha, p. 443"),
    "navamsa": ("The lagna's navamsa not movable", "Muhurta Chintamani 13.4 commentary, p. 442"),
    "houses_4_8": ("The 4th and 8th houses empty of every planet", "Muhurta Chintamani 13.4 and commentary, p. 443"),
    "moon_house": ("The Moon not in the 1st, 6th, 8th or 12th from the lagna", "Vasishtha in Muhurta Chintamani 13.3-4 commentary"),
    "bhadra": ("Bhadra on earth removed from the window, as for marriage", "Muhurta Chintamani 1.43-45; 13.1 commentary, p. 439"),
    "bad_yoga": ("The bad yogas' opening ghatis, Parigha's first half, and Vyatipata and Vaidhriti whole, removed, as for marriage", "Muhurta Chintamani 1.34-35; 13.1 commentary, p. 439"),
    "gandanta_tithi": ("One ghatika either side of the ends of the 5th, 10th and 15th tithis, removed", "Muhurta Chintamani 6.41, p. 265; 13.1 commentary, p. 439"),
    "gandanta_nakshatra": ("Two ghatikas either side of Ashlesha-Magha, Jyeshtha-Mula and Revati-Ashvini, removed", "Muhurta Chintamani 6.41, p. 265; 13.1 commentary, p. 439"),
    "sankranti": ("16.5 ghatikas either side of the Sun's sign change, removed (half of MC's 33 each side, our reading)", "Muhurta Chintamani 6.78, p. 293; 13.1 commentary, p. 439"),
    "mahapata": ("Mahapata, equal declinations of the Sun and Moon, removed", "Muhurta Chintamani 6.59; 13.1 commentary, p. 439"),
    "utpata": ("Utpata yoga, the weekday's star in MC 1.30's utpata column (28 nakshatras), removed", "Muhurta Chintamani 1.30, p. 23"),
    "marana": ("Mrtyu yoga, the weekday's star in MC 1.30's mrtyu column, removed", "Muhurta Chintamani 1.30, p. 23"),
    "kana": ("Kana yoga, the weekday's star in MC 1.30's kana column (Monday's is Abhijit), removed", "Muhurta Chintamani 1.30, p. 23"),
    "dagdha": ("Dagdha yoga, Narada's burnt weekday-star pairs, removed", "Narada in Muhurta Chintamani 1.5 commentary, p. 13"),
    "visha": ("A siddhi (amrta) weekday-star pair on its tithi, which turns it to visha, removed", "Muhurta Chintamani 1.20-21, pp. 19-20"),
    "middling_month": ("Excluded: Kartika or Margashirsha, which Narada counts middling for house entry, outside MC 13.1's northern course", "Narada in Muhurta Chintamani 13.1 commentary, p. 438"),
    "infancy_old": ("Excluded: Jupiter's or Venus's infancy or old age beyond 3 days", "Muhurta Chintamani 5.27 (5.28 gives 3 as the shortest)"),
    "krishna_after_dashami": ("The dark fortnight after Dashami: Vasishtha keeps the dark fortnight only up to Dashami", "Vasishtha in Muhurta Chintamani 13.1 commentary, p. 438"),
    "saturday": ("Saturday: stability, with a fear of thieves", "Vasishtha in Muhurta Chintamani 13.4 commentary, p. 443"),
}  # fmt: skip
GRIHA_PRAVESH_NOTES = {
    "vastuPuja": "The vastu-puja and bhuta-bali are done the day before entry, under the soft, fixed, swift or movable stars or Mula (Muhurta Chintamani 13.3a, 1925 printing p. 441; Dharmasindhu p. 242).",
    "door": "The door's direction sets the tithi class and the side the Sun must be on (Muhurta Chintamani 13.5). The muhurta finder applies them when a door direction is given; this list does not.",
    "oldHouse": "An old house, or one rebuilt after fire or flood, also allows Margashirsha, Kartika and Shravana and four more stars, without the checks on Jupiter and Venus (Muhurta Chintamani 13.2). The muhurta finder's old-house option applies it; this list is for a new house.",
    "owner": "The lagna should not be the 8th sign from the owner's birth lagna or Moon sign, and is best 3rd, 6th, 10th or 11th from them (Muhurta Chintamani 13.1, 13.4). These need the owner's chart and are not applied here.",
    "placements": "Benefics in a trine, a kendra, or the 11th, 2nd or 3rd, and malefics in the 3rd, 6th or 11th, are preferred (Muhurta Chintamani 13.3b). Not applied here.",
    "months": "Narada counts Kartika and Margashirsha as middling months for house entry (Muhurta Chintamani 13.1 commentary, p. 438); Muhurta Chintamani's verse asks for the Sun's northern course, so this list keeps to the four best months.",
}  # fmt: skip
# attributes.md: each sign's element as its verse names it (Tajika-nilakanthi 1.2-13).
TAJIKA_NILAKANTHI = {
    "text": "Tajika-nilakanthi",
    "edition": "Nilakantha Daivajna, with Pt. Sitarama's Hindi commentary rev. Ganeshadatta Pathaka, Bhargava Pustakalaya, Benares, 1937-38",
    "page": "2-6",
}
VIRGO_ELEMENT_NOTE = (
    "BPHS 5 calls Virgo prabhanjini, 'wind', which its 1939 commentary reads as air."
)
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
        "dhanteras_pradosha": ("Dhanteras: the dark Trayodashi current at pradosha, when the lamp for Yama is set outside", "Nirnaya-sindhu p. 294; Dharmasindhu p. 76"),
        "dhanteras_both_later": ("The Trayodashi at pradosha on both days: the later day, as a dark Trayodashi is taken on the later day", "Dharmasindhu p. 20"),
        "dhanteras_neither_later": ("The Trayodashi at pradosha on neither day: the later day", "Dharmasindhu p. 20"),
        "naraka_moonrise": ("Naraka-caturdashi: the Caturdashi current at the pre-dawn moonrise", "Dharmasindhu p. 76; Nirnaya-sindhu p. 294"),
        "naraka_moonrise_both_earlier": ("The Caturdashi at moonrise on both days: the earlier", "Dharmasindhu p. 76; Nirnaya-sindhu p. 295"),
        "naraka_began_before_sunrise": ("At moonrise on neither day, beginning between the first day's moonrise and sunrise: that dawn, from its start to sunrise", "Dharmasindhu pp. 76-77"),
        "naraka_later_moonrise": ("At moonrise on neither day otherwise: the second day, at moonrise", "Dharmasindhu p. 77"),
        "govardhan_nine_muhurtas": ("Govardhana-puja and Bali-pratipada: the Pratipada at sunrise lasting nine muhurtas or more after it puts every rite on that day (ten in the text; nine to ten our reading)", "Dharmasindhu p. 78"),
        "govardhan_earlier": ("Lasting under nine muhurtas: Bali's worship, the cow play, the Govardhana-puja and the margapali on the Amavasya-joined day before; the bath, new clothes and nirajana stay on the sunrise day (bathDate)", "Dharmasindhu p. 78"),
        "govardhan_no_sunrise_earlier": ("A Pratipada touching no sunrise: the day it begins, joined with the Amavasya (our reading of DS's rule)", "Dharmasindhu p. 78"),
        "bhai_dooj_earlier_alone": ("Bhai Dooj (Yama-dvitiya): the Dvitiya covers the afternoon on the earlier day alone: that day", "Dharmasindhu p. 79"),
        "bhai_dooj_later": ("Otherwise, the afternoon covered on both days or on neither: the later day", "Dharmasindhu p. 79"),
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
    "dhanteras": "The dark Trayodashi two days before the Dipavali Amavasya. The texts give one rite for it: a lamp for Yama set outside the house at nightfall, so that untimely death is averted (Skanda via the Nirnayamrta, NS p. 294; DS p. 76). yamaDipa is that day's pradosha while the Trayodashi runs, or the whole pradosha when it runs at neither. Nirnaya-sindhu's print reads 'the bright fortnight'; its own Hindi, its order and DS put it in the dark one. The names Dhanteras and Dhanvantari, and buying metal, are not in NS or DS. Narada has lamps waved in the early night for five tithis from the dark Dvadashi (NS p. 294, DS p. 76).",
    "narakaChaturdashi": "An oil bath with sesame oil before sunrise, at moonrise (Bhavishyottara via Hemadri, NS p. 294; DS p. 76). Of the night's last yama, arunodaya (four ghatikas before sunrise, NS p. 297) and moonrise to sunrise, each later time is better; abhyangaSnana is the main time, from moonrise or the Caturdashi's start to sunrise. If none can be kept, the bath is still taken after sunrise (DS p. 77). Apamarga is waved during the bath and Yama-tarpana follows (NS pp. 297-298, DS p. 77); lamps are given at pradosha (lamps), at that day's sunset even when the bath fell on the second day (DS p. 76). The Divodasiya gives the lamps on the first evening and the bath the next morning (NS p. 297).",
    "govardhan": "The Kartika shukla Pratipada: the oil bath, Bali's worship, the cow play and Govardhana-puja, the margapali, new clothes and the women's nirajana (DS p. 78). Govardhana is worshipped in the morning (Skanda via Hemadri, NS p. 303): govardhanPuja is the morning, the 1st fifth of the daytime (our reading of NS p. 28), while the Pratipada runs. Bali is worshipped at night (Bhavishya, NS p. 301): baliPuja is that night. Away from the hill, Govardhana is made of cow-dung or as a heap of food, the annakuta (DS p. 78). variantDate is Nirnaya-sindhu's day (pp. 301-302): the later day only when the Pratipada reaches that day's sayahna, the 5th fifth of the daytime.",
    "bhaiDooj": "Yama-dvitiya: Yamuna fed Yama, her brother, at her home on this day (DS p. 79; NS p. 305). A man eats from his sister's hand, not at home, and honours his sisters with clothes and ornaments. yamaPuja is the afternoon, the 4th fifth of the daytime, when Yama is worshipped with Citragupta and his messengers (DS p. 79; Skanda via Hemadri, NS p. 304). NS reports two other views without choosing: the Nirnayamrta takes the Dvitiya joined with the Pratipada, Hemadri the one covering midday.",
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
    "bhadra_face": "Bhadra's face (MC 1.44)",
    "bhadra_tail": "Bhadra's tail: no penalty (MC 1.44)",
    "bhadra_day_night": "Bhadra in a tithi's second half by day, or first half at night: no penalty (MC 1.44)",
    "adhika_masa_home": "Adhika month (MC 1.47)", "month_home": "Month without house entry (MC 13.1, 13.4)",
    "dakshinayana": "The Sun's southern course (MC 13.1)",
    "weekday_home": "Sunday or Tuesday: no house entry (MC 13.4)",
    "middling_month_home": "Kartika or Margashirsha: middling, for necessity (Narada in MC 13.1)",
    "sun_sign_home": "The Sun in Cancer, Virgo or Aquarius (Guru in MC 13.1)",
    "jupiter_venus_state": "Jupiter or Venus set, old or infant (MC 1.46-48, 5.27)",
    "jupiter_sign": "Jupiter in Leo or Capricorn (MC 1.48)",
    "movable_lagna_home": "Movable lagna (MC 13.4)", "movable_navamsa": "Movable navamsa (MC 13.4 commentary)",
    "house_4_8_occupied": "A planet in the 4th or 8th (MC 13.4)",
    "moon_1_6_12": "The Moon in the 1st, 6th or 12th (Vasishtha in MC 13.3-4)",
    "pot_chakra": "Pot chakra: the Moon's star 1st-5th or 14th-21st from the Sun's (MC 13.6; DS p. 242)",
    "door_tithi": "Tithi not of the door's class (MC 13.5)",
    "door_sun": "The Sun not on the left for the door (MC 13.4-5)",
    "utpata_yoga": "Utpata yoga (MC 1.30)", "kana_yoga": "Kana yoga (MC 1.30)",
    "mahapata": "Mahapata, equal declinations (MC 1.34)", "siddhi_yoga": "Siddhi yoga (MC 1.30)",
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
    "chandrashtama", "disha_shool", "visha_yoga", "siddhi_pair_act_ban", "bhadra_face",
    "utpata_yoga", "kana_yoga", "mahapata", "adhika_masa_home", "month_home", "dakshinayana", "weekday_home",
    "sun_sign_home", "jupiter_venus_state", "jupiter_sign", "movable_lagna_home", "movable_navamsa",
    "house_4_8_occupied", "moon_1_6_12", "pot_chakra", "door_tithi", "door_sun",
}  # fmt: skip
SUPPORTS = {
    "amrita_siddhi", "sarvartha_siddhi", "lagna_lord_strong", "benefic_kendra", "abhijit",
    "moon_ahead", "yogini_behind", "char_choghadiya", "movable_lagna", "fixed_lagna",
    "favoured_hora", "siddhi_yoga", "bhadra_tail", "bhadra_day_night",
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
            "elementSource": {**TAJIKA_NILAKANTHI, "verse": f"1.{i + 2}"},
            "elementNote": VIRGO_ELEMENT_NOTE if i == 5 else None,
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
        "gocharaNotes": GOCHARA_NOTES,
        "vivahRules": {k: {"name": n, "source": src} for k, (n, src) in VIVAH_RULES.items()},
        "vivahNotes": VIVAH_NOTES,
        "grihaPraveshRules": {
            k: {"name": n, "source": src} for k, (n, src) in GRIHA_PRAVESH_RULES.items()
        },
        "grihaPraveshNotes": GRIHA_PRAVESH_NOTES,
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
            f"D{d}": {
                "name": VARGA_NAMES[d],
                "signifies": VARGA_USES[d][0],
                "source": {**BPHS_1939, "verse": VARGA_USES[d][1]},
                "modernReading": VARGA_USES[d][2],
            }
            for d in VARGA_NAMES
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
