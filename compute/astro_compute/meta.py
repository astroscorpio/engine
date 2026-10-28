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
from .observances import EKADASHI_NAMES, NAME_NOTES, NS_P51

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
    "rahu_kalam": ("Rahu Kalam", "One eighth of the daylight, fixed by weekday; avoided for auspicious beginnings."),
    "yamaganda": ("Yamaganda", "Jupiter's eighth of the daylight; avoided for auspicious beginnings."),
    "gulika": ("Gulika Kalam", "Saturn's eighth of the daylight; avoided for auspicious beginnings."),
    "durmuhurta": ("Durmuhurta", "Daytime muhurtas marked inauspicious for the weekday."),
    "bad_yoga": ("Inauspicious yoga", "The opening ghatis of Vishkambha (3), Vajra (3), Shula (5), Ganda and Atiganda (6) and Vyaghata (9), the first half of Parigha, and all of Vyatipata and Vaidhriti."),
    "vishti": ("Bhadra (Vishti karana)", "Vishti karana, avoided while Bhadra resides on earth (Moon in Cancer, Leo, Aquarius or Pisces). Elsewhere its effect falls in that world."),
}  # fmt: skip
# docs/sources/methodology.md and panchang-yogas.md.
WINDOW_SOURCES = {
    "rahu_kalam": "Kālaprakāśikā pp. 175–176",
    "yamaganda": "Kālaprakāśikā pp. 175–176",
    "gulika": "Kālaprakāśikā pp. 175–176",
    "durmuhurta": "Muhūrta-cintāmaṇi 6.52, p. 275",
    "abhijit": "Muhūrta-cintāmaṇi 6.50, p. 274 (the 8th day muhurta); 6.52, p. 275 (not on Wednesday)",
    "bad_yoga": "Muhūrta-cintāmaṇi 1.34–35, p. 28; Nirṇaya-sindhu p. 33 (Vajra 9 in Muhūrta-mārtaṇḍa v. 2, p. 3)",
    "vishti": "Muhūrta-cintāmaṇi 1.43–45, pp. 35–38",
    "pradosha": "Muhūrta-cintāmaṇi 3.6 commentary, p. 125 (Skanda); Nirṇaya-sindhu p. 29; Vīramitrodaya, Samaya-prakāśa, p. 129",
}
# A note windows share, served once under windowNotes and pointed to by each window's noteKey (the
# lead, 18 Oct 2026): the names of the eighths and the commentary's half-eighth rule (hindi-terms.md,
# decisions 1-2), decision 1's sentence first.
WINDOW_SHARED_NOTES = {
    "eighths": "In the Bṛhat Parāśara Horā-śāstra (1933 printing), Saturn's eighth of the day is gulika and Jupiter's is yamaghaṇṭaka (BPHS 1933 PK 2.67–70, pp. 11–12). Kaśyapa, quoted in the commentary on Muhūrta-cintāmaṇi 1.37, p. 32, puts kulika and yamaghaṇṭa in these same eighths. The commentary avoids only the latter half of each, and Vasiṣṭha, quoted there, says they do no harm at night. The windows here follow Kālaprakāśikā pp. 175–176: the whole eighth, every day."
}
WINDOW_NOTE_KEYS = {"gulika": "eighths", "yamaganda": "eighths"}
WINDOW_NOTES = {
    "pradosha": "Three muhurtas after sunset, a muhurta being a fifteenth of the night (MC 6.50–51, p. 274; our reading). The first 72 minutes are sandhya, the evening twilight (Nirṇaya-sindhu p. 29, Skanda). The Gauda view of two ghatikas (48 minutes) is rejected for vows by Nirṇaya-sindhu p. 29.",
    "brahma": "Current practice: the 14th of the night's 15 muhurtas, ending one muhurta before sunrise. Manusmṛti 4.92 names the brahma muhurta; Kullūka (1909, p. 149) reads it as the last yama of the night, and Govindarāja, as Kullūka reports him, as its last muhurta.",
}
# A window's `reason` (windows.abhijit.reason) in words, so the web never composes the note
# (the lead, 18 Oct 2026).
WINDOW_REASONS = {"wednesday": "Not used on Wednesdays"}
# gochara.md: what the gochara endpoint leaves to notes (the lead's rulings, 15 Oct 2026).
GOCHARA_NOTES = {
    "count": "Houses are counted from the Moon sign, which is the 1st (Phaladīpikā 26.1).",
    "exemptions": "The Sun and Saturn never block each other, nor do the Moon and Mercury (PD 26.3–6; MC 4.4a). The nodes neither have nor cause vedha (blocking by the seven grahas only is our reading).",
    "nodes": "Rahu and Ketu follow PD 26.2, like the Sun. Muhūrta-cintāmaṇi 4.1 treats them like Saturn instead: good in 3, 6 and 11, with Saturn's vedha (12, 9, 5).",
    "reverseVedha": "MC 4.4–5 also make a planet in a bad house good when another occupies its paired good house (vama-vedha), counted three ways by Nārada, Kaśyapa and the commentator. Not computed.",
    "brightMoon": "In the bright fortnight MC 4.4 also counts the Moon good in the 2nd, 5th and 9th unless blocked from the 6th, 8th and 4th (Nārada). Not computed; PD's lines for those houses are bad.",
    "timing": "Transits are classed by the sign occupied. PD 26.25: Mars and the Sun act in a sign's first third, Jupiter and Venus in the middle, the Moon and Saturn in the last, Mercury and Rahu throughout. MC 4.17's commentary has planets give the coming sign's results early (the Sun 5 days, Saturn 6 months). Neither is computed.",
    "neutralised": "Nārada (MC p. 144): a planet debilitated, in an enemy's sign or combust gives neither good nor bad transit results. Not computed.",
    "regional": "Kaśyapa (MC p. 144) holds that vedha applies only between the Himalaya and the Vindhya.",
    "wording": "The lines are classical statements from the 1937 translation, quoted with their verses; some speak of death or danger to life. They are not forecasts.",
}  # fmt: skip
# vivah.md (the lead's decisions of 15 Oct 2026): rule ids for /muhurat/vivah.
VIVAH_RULES = {
    "season_best": ("Magha, Phalguna, Vaishakha or Jyeshtha (amanta): best", "Muhūrta-cintāmaṇi 6.13 commentary, p. 235 (Nārada); Dharmasindhu p. 181"),
    "season_middling": ("Ashadha shukla 1-10, Kartika from shukla 11, or Margashirsha: middling", "Muhūrta-cintāmaṇi 6.13 commentary, p. 235; 5.26, p. 186"),
    "chaturmas": ("Hari's sleep, Ashadha shukla 11 to Kartika shukla 11: barred", "Muhūrta-cintāmaṇi 6.13 commentary, p. 235"),
    "off_season": ("A lunar month outside the season (Pausha, Chaitra, Shravana, Bhadrapada, Ashvina): barred, or for Pausha and Chaitra excluded when the Sun's sign is allowed", "Muhūrta-cintāmaṇi 6.13, p. 234, with the commentary, p. 235"),
    "sun_sign": ("The Sun in Pisces, Sagittarius or Leo: barred", "Garga in Muhūrta-cintāmaṇi 6.13 commentary, p. 235"),
    "adhika_month": ("An adhika or kshaya month, and the adhika months around a kshaya month: barred", "Muhūrta-cintāmaṇi 1.47, p. 38, with the commentary, p. 40; Dharmasindhu p. 4"),
    "jupiter_set": ("Jupiter within 11 time-degrees of the Sun: set", "Sūrya-siddhānta 9.6–7; Muhūrta-cintāmaṇi 1.46–48, 5.26"),
    "jupiter_old": ("The 15 days before Jupiter sets", "Muhūrta-cintāmaṇi 5.27"),
    "jupiter_infant": ("The 15 days after Jupiter rises", "Muhūrta-cintāmaṇi 5.27"),
    "venus_set": ("Venus within 8 time-degrees of the Sun (retrograde) or 10 (direct): set", "Sūrya-siddhānta 9.6–7; Muhūrta-cintāmaṇi 1.46–47, 5.26"),
    "venus_old": ("The 15 days before Venus sets in the east, or the 5 before it sets in the west", "Muhūrta-cintāmaṇi 5.27"),
    "venus_infant": ("The 3 days after Venus rises in the east, or the 10 after it rises in the west", "Muhūrta-cintāmaṇi 5.27"),
    "jupiter_sign": ("Jupiter in Leo or Capricorn: barred for its whole stay", "Muhūrta-cintāmaṇi 1.48, p. 40"),
    "tuesday": ("Tuesday: always avoided", "Vasiṣṭha in Muhūrta-cintāmaṇi 6.53"),
    "nakshatra": ("The Moon in Mrgashira, Hasta, Mula, Anuradha, Magha, Rohini, Revati, the three Uttaras or Svati", "Muhūrta-cintāmaṇi 6.53, p. 275; Dharmasindhu p. 181"),
    "vedha": ("Not pierced: a malefic anywhere in the paired star bars the whole star, a benefic only the Moon's paired quarter (1-4, 2-3)", "Muhūrta-cintāmaṇi 6.54, p. 276"),
    "tithi": ("Not a rikta tithi (4, 9, 14) or Amavasya", "Muhūrta-cintāmaṇi 6.53, p. 275"),
    "bhadra": ("Bhadra on earth removed from the window", "Muhūrta-cintāmaṇi 1.43–45; Dharmasindhu p. 181"),
    "bad_yoga": ("The bad yogas' opening ghatis, Parigha's first half, and Vyatipata and Vaidhriti whole, removed", "Muhūrta-cintāmaṇi 1.34–35; Dharmasindhu p. 181"),
    "gandanta_tithi": ("One ghatika either side of the ends of the 5th, 10th and 15th tithis, removed", "Muhūrta-cintāmaṇi 6.41, p. 265"),
    "gandanta_nakshatra": ("Two ghatikas either side of Ashlesha-Magha, Jyeshtha-Mula and Revati-Ashvini, removed", "Muhūrta-cintāmaṇi 6.41, p. 265"),
    "gandanta_lagna": ("Half a ghatika either side of the lagna's Cancer-Leo, Scorpio-Sagittarius and Pisces-Aries boundaries, removed", "Muhūrta-cintāmaṇi 6.41, p. 265"),
    "sankranti": ("16.5 ghatikas either side of the Sun's sign change, removed (half of MC's 33 each side, our reading)", "Muhūrta-cintāmaṇi 6.78, p. 293"),
    "mahapata": ("Mahapata, equal declinations of the Sun and Moon, removed", "Muhūrta-cintāmaṇi 6.59"),
    "eclipse": ("Days after and before an eclipse visible here: 3 and 1.5 for a quarter of the disc, 4 and 2 for half, 6 and 3 for three quarters, 8 and 4 for total (bins ours)", "Dharmasindhu p. 181, note"),
    "solar_month": ("Excluded: the lunar month is not one of the season's, though the Sun's sign is (the solar-month count MC's commentary sets aside)", "Muhūrta-cintāmaṇi 6.13 commentary, p. 235"),
    "rikta": ("Excluded: a rikta tithi (Chaturthi, Navami, Chaturdashi)", "Muhūrta-cintāmaṇi 6.53, p. 275"),
    "vedha_slow": ("Excluded: pierced only by a slow planet (Jupiter, Saturn, Rahu, Ketu) sitting in the paired star", "Muhūrta-cintāmaṇi 6.54, p. 276"),
    "infancy_old": ("Excluded: Jupiter's or Venus's infancy or old age beyond 3 days", "Muhūrta-cintāmaṇi 5.27 (5.28 gives 3 as the shortest)"),
    "utpata": ("Utpata yoga, the weekday's star in the utpata column of MC 1.30 (28 nakshatras), removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "marana": ("Mrtyu yoga, the weekday's star in the mrtyu column of MC 1.30, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "kana": ("Kana yoga, the weekday's star in the kana column of MC 1.30 (Monday's is Abhijit), removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "dagdha": ("Dagdha yoga, Nārada's burnt weekday-star pairs, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Nārada in Muhūrta-cintāmaṇi 1.5 commentary, p. 13"),
    "visha": ("A siddhi (amrta) weekday-star pair on its tithi, which turns it to visha, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.20–21, pp. 19–20"),
    "godhuli": ("Godhuli, the alternative: half a ghatika either side of sunset; Thursday only after it, Saturday only before; none with the Moon 1st, 6th or 8th from the lagna, or Mars 1st, 7th or 8th", "Muhūrta-cintāmaṇi 6.97–99, pp. 305–307"),
    "weak_tithi": ("Shashthi or Ashtami: 'little fruit' (DS); Vasiṣṭha drops them", "Dharmasindhu p. 181; Muhūrta-cintāmaṇi 6.53"),
    "middling_weekday": ("Sunday or Saturday: middling", "Vasiṣṭha in Muhūrta-cintāmaṇi 6.53; Dharmasindhu p. 181"),
    "middling_weekday_dvadashi_trayodashi": ("Sunday or Saturday on a Dvadashi or Trayodashi: of great fault (Vasiṣṭha, MC 6.53 commentary, p. 275); only Tuesday is barred outright", "Vasiṣṭha in Muhūrta-cintāmaṇi 6.53 commentary, p. 275"),
    "krishna_paksha": ("The dark fortnight: middling", "Dharmasindhu p. 181"),
    "no_clean_lagna": ("No lagna in the day's windows is free of every fault; godhuli, the cow-dust hour, is the texts' alternative", "Muhūrta-cintāmaṇi 6.97, p. 305"),
    "no_lagna": ("Excluded: no lagna in the windows clears the lagna rules (6.84's houses, the jamitra, kartari, the navamsa, 6.90's points), and godhuli is excluded by 6.99", "Muhūrta-cintāmaṇi 6.42–90, 6.97–99, pp. 268–307"),
}  # fmt: skip
VIVAH_NOTES = {
    "infancy": "Infancy and old age follow MC 5.27 by the side of the sky. MC 5.28 gives 10, 7 or 3 days as alternatives, and Dharmasindhu p. 5 takes 7 days either side as the middle view.",
    "setting": "Set means within the Sūrya-siddhānta 9.6–7 distance in time-degrees, measured here from the difference between the planet's and the Sun's rising (a morning planet) or setting (an evening one).",
    "jupiterLeo": "Dharmasindhu p. 5 relaxes Jupiter in Leo by region: barred everywhere only in Magha or the Leo portion; after it, no fault south of the Godavari or north of the Ganga, but between the two rivers marriage stays barred for the whole stay. Not applied.",
    "solarMonths": "The solar-month school also allows Kartika with the Sun in Scorpio, Pausha with the Sun in Capricorn and Caitra with the Sun in Aries; MC's commentator sets it aside except for a marriage that cannot wait, and Dharmasindhu allows it by local custom. Not applied.",
    "moreStars": "Haradatta adds Citra, Shravana, Dhanishtha and Ashvini (Dharmasindhu p. 181). Not applied.",
    "kharmas": "Kharmas, the popular name (not in the texts read), is the Sun in Dhanus or Mina, between the Dhanus and Makara sankrantis and between the Mina and Mesha sankrantis. Garga's bar (MC 6.13 commentary, p. 235) also includes the Sun in Leo.",
    "phase2": "The lagna rules of MC ch. 6 apply inside each window (lagnas): 6.84's houses, the jamitra, kartari, the navamsa, 6.90's points, purity, blind, deaf and lame lagnas and kuvarga, with 6.86–87's cancellations. The couple's own charts (MC 6.12, 6.14, 6.44) are not applied.",
    "lagnaReadings": "Our readings in the lagna rules: the waning Moon is the dark fortnight's Moon; Rahu and Ketu count in the jamitra; any fraction of MC 6.73's graded aspects counts as seeing; purity is judged by the lord's sign, not a navamsa chart; three benefic vargas are middling; 6.87 lifts the lame lagna as well as the blind and deaf; each vimsopaka edge belongs to the grade above.",
    "trivikrama": "Trivikrama treats the Moon and Jupiter in the 7th as neutral, and MC's commentary allows it as an option (6.84, p. 296). Not applied.",
    "strength66": "MC 6.66 clears the jamitra, kartari and the other lagna faults when the lagna has the strength of the Sun and the Moon. Noted, not applied.",
    "jupiter88": "MC 6.88–89 say every fault vanishes with Jupiter in a kendra or trine; the commentary limits it (the 7th, kulika and durmuhurta stay, and Nārada leaves a kartari lagna). Not applied.",
    "regional79": "Kaśyapa confines the blind, deaf and lame lagnas to Gauda and Malava (MC 6.81 commentary, p. 294). Applied everywhere here.",
}  # fmt: skip
# vivah.md "Phase 2" (V1-V10, the lead's decisions of 16 Oct 2026): the lagna's bars,
# faults and their weight, for windows[].lagnas and windows[].lagnaBars.
VIVAH_LAGNA_RULES = {
    "h1": ("The Moon or a malefic in the lagna", "Muhūrta-cintāmaṇi 6.84, p. 296", "bar"),
    "h3_venus": ("Venus in the 3rd", "Muhūrta-cintāmaṇi 6.84, p. 296", "bar"),
    "h6": ("The lagna lord, Venus or the Moon in the 6th; Venus in an enemy's sign or debilitated, or the Moon debilitated or in a debilitated navamsa, is excused (6.86)", "Muhūrta-cintāmaṇi 6.84 (p. 296), 6.86 (p. 298)", "bar"),
    "h7": ("Any planet in the 7th, Rahu and Ketu included (our reading): the jamitra from the lagna", "Muhūrta-cintāmaṇi 6.65 (p. 285), 6.84 (p. 296)", "bar"),
    "h8": ("The Moon, the lagna lord, a benefic or Mars in the 8th; Mars combust, in an enemy's sign or debilitated, or the Moon debilitated or in a debilitated navamsa, is excused (6.86)", "Muhūrta-cintāmaṇi 6.84 (p. 296), 6.86 (p. 298)", "bar"),
    "h10_mars": ("Mars in the 10th", "Muhūrta-cintāmaṇi 6.84, p. 296", "bar"),
    "h12_saturn": ("Saturn in the 12th", "Muhūrta-cintāmaṇi 6.84, p. 296", "bar"),
    "jamitra_moon": ("The Moon in the 55th navamsa from the Sun, Mars, Saturn, Rahu or Ketu (the navamsa opposite theirs), unless the Moon is exalted, in its own, a benefic's or a friend's sign, or aspected by a benefic", "Muhūrta-cintāmaṇi 6.65, p. 285, with the commentary, p. 286", "bar"),
    "kartari": ("Kartari: a malefic moving direct in the 12th and a retrograde one in the 2nd (Rahu and Ketu always retrograde; the Moon a malefic in the dark fortnight, our reading), unless both are in an enemy's sign, debilitated or combust (6.86)", "Muhūrta-cintāmaṇi 6.42 (pp. 268–270), 6.86 (pp. 298–299)", "bar"),
    "navamsa": ("The lagna's navamsa is not Gemini, Virgo, Libra or the first half of Sagittarius (Pisces and Dharmasindhu's Taurus and Cancer apart)", "Muhūrta-cintāmaṇi 6.82–83, pp. 294–295", "bar"),
    "last_navamsa": ("The last navamsa of the sign, unless vargottama", "Muhūrta-cintāmaṇi 6.83, p. 295", "bar"),
    "movable_navamsa": ("With the Moon in Libra or Capricorn, a movable navamsa in a movable lagna", "Muhūrta-cintāmaṇi 6.83, p. 295", "bar"),
    "vimsopaka": ("Under 5 of 6.90's 20 points: rejected", "Muhūrta-cintāmaṇi 6.90, p. 301, with the commentary, p. 302", "bar"),
    "purity_lagna": ("The groom's side is not pure: neither the navamsa's lord, the lagna lord nor a benefic friend of the navamsa's lord joins or aspects the lagna or its navamsa (any aspect fraction, by the lord's sign: our reading)", "Muhūrta-cintāmaṇi 6.73–76, pp. 290–292", "heavy"),
    "purity_seventh": ("The bride's side is not pure: the same test for the 7th and the 7th from the lagna's navamsa", "Muhūrta-cintāmaṇi 6.73–76, pp. 290–292", "heavy"),
    "kartari_moon": ("Kartari round the Moon, no benefic aspecting the Moon", "Kaśyapa in Muhūrta-cintāmaṇi 6.42 commentary, p. 268", "fault"),
    "kuvarga": ("Fewer than three of the lagna's six vargas (sign, hora, drekkana, navamsa, dvadashamsha, trimshamsha) ruled by benefics", "Vasiṣṭha in Muhūrta-cintāmaṇi 6.40 commentary, p. 265; Dharmasindhu p. 182", "fault"),
    "navamsa_pisces": ("A Pisces navamsa: only when no other lagna clears", "Muhūrta-cintāmaṇi 6.82 commentary, p. 295", "last_resort"),
    "vimsopaka_poor": ("5 to under 10 of 6.90's points: poor, only when no other lagna exists", "Muhūrta-cintāmaṇi 6.90, p. 301, with the commentary, p. 302", "last_resort"),
    "navamsa_ds_only": ("A Taurus or Cancer navamsa: good by Dharmasindhu only", "Dharmasindhu p. 182", "ds_only"),
    "blind_lagna": ("A blind lagna at its time (by day Leo, Aries, Taurus; by night Virgo, Gemini, Cancer), not aspected by its lord or Jupiter, nor lifted by Mercury, Jupiter or Venus in a kendra other than the 7th or a trine (6.87)", "Muhūrta-cintāmaṇi 6.79, 6.81, 6.87, pp. 293–294, 299", "light"),
    "deaf_lagna": ("A deaf lagna at its time (by day Libra, Scorpio; by night Capricorn, Sagittarius), not aspected by its lord or Jupiter, nor lifted under 6.87", "Muhūrta-cintāmaṇi 6.79, 6.81, 6.87, pp. 293–294, 299", "light"),
    "lame_lagna": ("A lame lagna at its time (by day Aquarius; by night Pisces), not aspected by its lord or Jupiter, nor lifted under 6.87 (our reading)", "Muhūrta-cintāmaṇi 6.79, 6.81, 6.87, pp. 293–294, 299", "light"),
    "moon_seventh_malefic": ("The Sun, Mars, Saturn, Rahu or Ketu elsewhere in the 7th sign from the Moon, the Moon not exalted, in its own, a benefic's or a friend's sign, nor aspected by a benefic", "the Dīpikā in Muhūrta-cintāmaṇi 6.84 commentary, pp. 296–297", "light"),
    "hemming_lagna": ("Malefics on both sides of the lagna without MC's kartari: the lesser hemming fault", "Muhūrta-cintāmaṇi 6.42 commentary, p. 268; Dharmasindhu p. 182", "light"),
    "hemming_moon": ("Malefics on both sides of the Moon without MC's kartari: the lesser hemming fault", "Muhūrta-cintāmaṇi 6.42 commentary, p. 268; Dharmasindhu p. 182", "light"),
}  # fmt: skip
VIVAH_LAGNA_GRADES = {
    "best": "15 or more of 6.90's 20 points (an edge goes to the grade above: our reading)",
    "middling": "10 to under 15 points",
    "poor": "5 to under 10 points: only when no other lagna exists",
    "rejected": "Under 5 points",
}
VIVAH_KUVARGA = {
    "good": "More than three of the six vargas ruled by benefics",
    "middling": "Exactly three (our reading)",
    "bad": "Fewer than three: kuvarga, one of Dharmasindhu's twenty-one great doshas",
}
# vivah.md "Phase 3" (P1-P8, the lead's decisions of 16 Oct 2026): the couple's own
# rules for /muhurat/vivah/personal (contract 7q). A remedy is the text's own statement.
MC_P271 = "Kaśyapa and Nārada in Muhūrta-cintāmaṇi 6.44 commentary, p. 271"
VIVAH_PERSONAL_RULES = {
    "sun_groom": ("The Sun good by gochara from the groom's Moon sign (with vedha)", "Muhūrta-cintāmaṇi 6.12, p. 232, with the commentary, p. 234; Phaladīpikā 26.2–3, pp. 286–287", "support", None),
    "sun_groom_weak": ("The Sun not good by gochara from the groom's Moon sign; the texts read give no remedy (a fault, not a bar: our reading)", "Muhūrta-cintāmaṇi 6.12, p. 232, with the commentary, pp. 233–234", "fault", None),
    "moon_good": ("The Moon good by gochara from the partner's Moon sign (with vedha)", "Muhūrta-cintāmaṇi 6.12; Dharmasindhu p. 181", "support", None),
    "moon_weak": ("The Moon not good by gochara for one partner", "Dharmasindhu p. 181", "fault", ("Dharmasindhu p. 181: if one of the two lacks the Moon's strength, a gift of silver or the like is made", "Dharmasindhu p. 181")),
    "moon_weak_both": ("The Moon not good by gochara for both partners (a bar, since the text's remedy is for one: our reading)", "Dharmasindhu p. 181", "bar", None),
    "tara_bad": ("The Moon's star is the 3rd, 5th or 7th tara (vipat, pratyari, vadha) from one partner's birth star, not lifted by the Moon in a benefic's sign and good by gochara (MC 5.32)", "Muhūrta-cintāmaṇi 4.18 commentary, p. 157; 5.32, p. 192", "fault", ("Muhūrta-cintāmaṇi 4.18: rock salt is the gift for a bad tara", "Muhūrta-cintāmaṇi 4.18, p. 157")),
    "tara_bad_both": ("A bad tara for both partners (a bar: our reading)", "Muhūrta-cintāmaṇi 4.18 commentary, p. 157", "bar", None),
    "birth_month": ("The first-born partner's birth month (amanta)", "Muhūrta-cintāmaṇi 6.14, p. 236; ch. 1 commentary, pp. 28–29", "bar", None),
    "birth_star": ("The Moon in the first-born partner's birth star", "Muhūrta-cintāmaṇi 6.14, p. 236", "bar", None),
    "birth_tithi": ("The first-born partner's birth tithi", "Muhūrta-cintāmaṇi 6.14, p. 236", "bar", None),
    "birth_muhurta": ("The muhurta of the day or night with the number of the first-born partner's birth muhurta (Vasiṣṭha; the numbering is our reading)", "Muhūrta-cintāmaṇi 6.14 commentary, p. 236", "bar", None),
    "birth_day_favourable": ("The birth month, star or tithi of a partner who is not the first-born: favourable", "Muhūrta-cintāmaṇi 6.14, p. 236 (Cyavana, Vaṭeśvara)", "support", None),
    "three_jyeshtha": ("Both partners first-born, in amanta Jyeshtha: the three jyeshthas", "Muhūrta-cintāmaṇi 6.15, p. 236; Dharmasindhu p. 181", "bar", None),
    "eldest_jyeshtha": ("One first-born partner, in Jyeshtha: middling, only when there is no other way", "Muhūrta-cintāmaṇi 6.15 commentary, p. 236; Dharmasindhu p. 181", "light", None),
    "eighth_lagna": ("The 8th sign from a partner's birth lagna or Moon sign rising, unless it is one of the exempt signs (MC 6.45), or Guru's remedy holds: the lagna lord in a kendra aspected by a benefic, in its own or a benefic's navamsa, exalted, or in its own or a friend's sign (friendship by BPHS: our reading)", "Muhūrta-cintāmaṇi 6.44–45, pp. 271–272", "bar", None),
    "janma_rashi_rising": ("A partner's birth Moon sign rising", MC_P271, "fault", None),
    "janma_lagna_rising": ("A partner's birth lagna rising, or an upacaya sign (3, 6, 10, 11) from their birth lagna or Moon sign", MC_P271, "support", None),
    "no_lagna": ("No lagna and no godhuli left for the couple", "Muhūrta-cintāmaṇi 6.97–99", "bar", None),
}  # fmt: skip
# What lifted a rule that would otherwise apply, for `lifted` in 7i lagnas and 7q marks.
GURU_P272 = "Guru in Muhūrta-cintāmaṇi 6.45 commentary, p. 272"
VIVAH_LIFTS = {
    "mc_6_86": ("Cancelled by MC 6.86: an enemy's sign, debilitation or combustion (for kartari, both malefics; for the Moon, debilitated or in a debilitated navamsa)", "Muhūrta-cintāmaṇi 6.86, p. 298"),
    "moon_sign": ("The Moon exalted, or in its own, a benefic's or a friend's sign", "Rājamārtaṇḍa and Vyavahārasamuccaya in Muhūrta-cintāmaṇi 6.65 commentary, p. 286"),
    "moon_aspected": ("The Moon aspected by a benefic", "Rājamārtaṇḍa and Vyavahārasamuccaya in Muhūrta-cintāmaṇi 6.65 commentary, p. 286"),
    "benefic_aspect": ("A benefic aspecting the Moon", "Kaśyapa in Muhūrta-cintāmaṇi 6.42 commentary, p. 268"),
    "lord_or_jupiter_aspect": ("The sign's lord or Jupiter aspecting the lagna", "Muhūrta-cintāmaṇi 6.81, p. 294"),
    "mc_6_87": ("Mercury, Jupiter or Venus in a kendra other than the 7th, or in a trine", "Muhūrta-cintāmaṇi 6.87, p. 299"),
    "mc_5_32": ("The Moon in a benefic's sign and good by gochara for that partner", "Muhūrta-cintāmaṇi 5.32, p. 192"),
    "guru_kendra_aspect": ("Guru's remedy: the lagna lord in a kendra, aspected by a benefic", GURU_P272),
    "guru_navamsa": ("Guru's remedy: the lagna lord in its own or a benefic's navamsa", GURU_P272),
    "guru_exalted": ("Guru's remedy: the lagna lord exalted", GURU_P272),
    "guru_own_friend": ("Guru's remedy: the lagna lord in its own or a friend's sign (friendship as in BPHS 1933 PK 2.53–58, p. 8; our reading)", GURU_P272),
}  # fmt: skip
VIVAH_JUPITER_BRIDE = {
    "best": "Jupiter in the 2nd, 5th, 7th, 9th or 11th from the bride's Moon sign",
    "worship": "In the 1st, 3rd, 6th or 10th: with worship",
    "condemned": "In the 4th, 8th or 12th",
}
VIVAH_PERSONAL_NOTES = {
    "jupiterBride": "MC p. 233 grades Jupiter from the bride's Moon sign; Vyāsa (p. 234) says a bride past ten needs only the tara, the Moon and the lagna, so it is shown for information.",
    "bothEldest": "Both partners first-born: Dharmasindhu (p. 181) calls months other than Jyeshtha middling; MC's commentary rejects even that and records Garga's view that an eldest son and an eldest daughter should not marry each other (p. 237). It changes no date.",
    "vrddhaGarga": "Vṛddha-Garga counts the birth month as thirty days from the birthday (MC 1.34 commentary, p. 28). Not applied.",
    "jaganmohana": "In necessity the Jaganmohana narrows the first-born bar: Vasiṣṭha keeps only the birth day, Atri three days, Bhāguri the birth fortnight (MC pp. 28, 236). Not applied.",
    "naradaNavamsa": "Nārada would also avoid the navamsas of the 8th sign (MC p. 272). Not applied.",
    "ashtakavarga": "Nārada lets ashtakavarga strength stand in when the gochara fails (MC p. 234); it is not computed here.",
    "godhuli": "Godhuli stands in for the lagna only on an otherwise valid day, so the couple's Moon, tara and first-born tests apply to it (MC 6.97 commentary, p. 306).",
    "starOnly": "A partner given by birth star has no birth lagna, month or tithi, so the rules needing them are skipped (partners.skipped).",
}  # fmt: skip
# mundan.md (the lead's decisions of 15 Oct 2026): rule ids for /muhurat/mundan.
MUNDAN_RULES = {
    "month": ("Not Caitra, nor an adhika or kshaya month", "Muhūrta-cintāmaṇi 5.29, 1.47; Dharmasindhu p. 137"),
    "off_season": ("Caitra: barred", "Muhūrta-cintāmaṇi 5.29"),
    "adhika_month": ("An adhika or kshaya month: barred", "Muhūrta-cintāmaṇi 1.47; Dharmasindhu p. 137"),
    "dakshinayana": ("The Sun in its southern course, Cancer to Sagittarius: barred", "Muhūrta-cintāmaṇi 5.26, 5.29"),
    "jupiter_set": ("Jupiter within 11 time-degrees of the Sun: set", "Sūrya-siddhānta 9.6–7; Muhūrta-cintāmaṇi 5.26"),
    "jupiter_old": ("The 15 days before Jupiter sets", "Muhūrta-cintāmaṇi 5.27"),
    "jupiter_infant": ("The 15 days after Jupiter rises", "Muhūrta-cintāmaṇi 5.27"),
    "venus_set": ("Venus within 8 time-degrees of the Sun (retrograde) or 10 (direct): set", "Sūrya-siddhānta 9.6–7; Muhūrta-cintāmaṇi 5.26"),
    "venus_old": ("The 15 days before Venus sets in the east, or the 5 before it sets in the west", "Muhūrta-cintāmaṇi 5.27"),
    "venus_infant": ("The 3 days after Venus rises in the east, or the 10 after it rises in the west", "Muhūrta-cintāmaṇi 5.27"),
    "jupiter_sign": ("Jupiter in Leo or Capricorn: barred for its whole stay", "Muhūrta-cintāmaṇi 1.48, pp. 40–41 (Varāha); Dharmasindhu p. 5"),
    "nakshatra": ("The Moon in Ashvini, Mrgashira, Punarvasu, Pushya, Hasta, Citra, Svati, Jyeshtha, Shravana, Dhanishtha, Shatabhisha or Revati", "Muhūrta-cintāmaṇi 5.29; Vasiṣṭha, p. 190; Dharmasindhu p. 137"),
    "tithi": ("Tithi 2, 3, 5, 7, 10, 11 or 13", "Muhūrta-cintāmaṇi 5.29; Vasiṣṭha, p. 190; Dharmasindhu p. 137"),
    "weekday": ("Wednesday, Thursday or Friday, or Monday in the bright fortnight", "Muhūrta-cintāmaṇi 5.29; Parāśara, p. 190"),
    "lagna": ("The lagna and its navamsa in a benefic's sign: Taurus, Gemini, Cancer, Virgo, Libra, Sagittarius or Pisces", "Muhūrta-cintāmaṇi 5.29 ('lagnamshayoh'); Kaśyapa, p. 190"),
    "house_8": ("The 8th house empty, except for Venus", "Muhūrta-cintāmaṇi 5.29; Parāśara, p. 190"),
    "kendra_malefic": ("No waning Moon, Mars, Saturn or Sun in a kendra (death, death by weapon, lameness, fever); the Moon counts as waning outside tithis 9-22, as the engine reads BJ 2.5", "Muhūrta-cintāmaṇi 5.30"),
    "bhadra": ("Bhadra on earth removed from the window", "Muhūrta-cintāmaṇi 1.43–45"),
    "bad_yoga": ("The bad yogas' opening ghatis, Parigha's first half, and Vyatipata and Vaidhriti whole, removed", "Muhūrta-cintāmaṇi 1.34–35"),
    "gandanta_tithi": ("One ghatika either side of the ends of the 5th, 10th and 15th tithis, removed", "Muhūrta-cintāmaṇi 6.41, p. 265"),
    "gandanta_nakshatra": ("Two ghatikas either side of Ashlesha-Magha, Jyeshtha-Mula and Revati-Ashvini, removed", "Muhūrta-cintāmaṇi 6.41, p. 265"),
    "gandanta_lagna": ("Half a ghatika either side of the lagna's Cancer-Leo, Scorpio-Sagittarius and Pisces-Aries boundaries, removed", "Muhūrta-cintāmaṇi 6.41, p. 265"),
    "sankranti": ("16.5 ghatikas either side of the Sun's sign change, removed (half of MC's 33 each side, our reading)", "Muhūrta-cintāmaṇi 6.78, p. 293"),
    "mahapata": ("Mahapata, equal declinations of the Sun and Moon, removed", "Muhūrta-cintāmaṇi 6.59"),
    "utpata": ("Utpata yoga, the weekday's star in the utpata column of MC 1.30 (28 nakshatras), removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "marana": ("Mrtyu yoga, the weekday's star in the mrtyu column of MC 1.30, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "kana": ("Kana yoga, the weekday's star in the kana column of MC 1.30 (Monday's is Abhijit), removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "dagdha": ("Dagdha yoga, Nārada's burnt weekday-star pairs, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Nārada in Muhūrta-cintāmaṇi 1.5 commentary, p. 13"),
    "visha": ("A siddhi (amrta) weekday-star pair on its tithi, which turns it to visha, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.20–21, pp. 19–20"),
    "krishna_last_three": ("A dark Trayodashi: DS keeps the dark fortnight except its last three days", "Dharmasindhu p. 137"),
    "infancy_old": ("Excluded: Jupiter's or Venus's infancy or old age beyond 3 days", "Muhūrta-cintāmaṇi 5.27 (5.28 gives 3 as the shortest)"),
    "barred_stretches": ("Bhadra on earth, the bad yogas' openings, gandanta, the sankranti and mahapata, removed from the windows", "Muhūrta-cintāmaṇi 1.34–35, 1.43–45, 6.41, 6.59, 6.78"),
}  # fmt: skip
MUNDAN_NOTES = {
    "age": "From the 3rd year, in an odd year: the 3rd, 5th or 7th, counted from conception or from birth (MC 5.29; Vasiṣṭha, p. 189). Dharmasindhu p. 137 also allows the 1st, 2nd, 3rd or 5th year, or with the upanayana, by family custom; families who tonsure with the upanayana use its muhurta.",
    "birthStar": "The child's birth star: Kaśyapa calls it good for a Vedic tonsure (MC p. 190), Dharmasindhu p. 137 avoids it for any shave. The muhurta finder excludes it when a chart is given.",
    "child": "With the child's chart, the muhurta finder also bars the birth month (Rājamārtaṇḍa, MC p. 190), the 8th sign from the birth lagna or Moon sign (MC 5.29) and an unfavourable tara (MC 5.30; exceptions in 5.32). For an eldest child Jyeshtha is barred (Ratnamālā, MC 5.33 commentary, p. 193); some add Margashirsha.",
    "mother": "Not while the mother is past the fifth month of pregnancy, unless the child is over five or the tonsure is done with the upanayana (MC 5.31, p. 191; Nārada; Dharmasindhu p. 137). Dharmasindhu also bars a child with fever, the six months after an upanayana or marriage in the family, and the time before a death in the family is ritually closed.",
    "varna": "Prayoga-pārijāta (MC p. 190) and Dharmasindhu p. 137 allow Sunday for brahmanas, Tuesday for kshatriyas and Saturday for vaishyas and shudras. This list keeps to the weekdays allowed for all.",
    "months": "Dharmasindhu p. 137 names Magha, Phalguna, Vaishakha and Jyeshtha as good months; Muhūrta-cintāmaṇi asks for the Sun's northern course and not Caitra, which this list applies.",
    "placements": "Malefics are best in the 3rd, 6th or 11th, benefics in a kendra (MC 5.29–30), and Kaśyapa keeps the Moon out of the 6th, 8th and 12th (p. 191). Not applied here.",
}  # fmt: skip
# samskaras.md (the lead's decisions of 15 Oct 2026)
ANNAPRASHAN_RULES = {
    "adhika_month": ("Not an adhika or kshaya month", "Dharmasindhu pp. 4, 135"),
    "fortnight": ("The bright fortnight", "Nārada in Muhūrta-cintāmaṇi 5.17 commentary, p. 179"),
    "tithi": ("Tithi 2, 3, 5, 7, 10 or 13 of the bright fortnight", "Muhūrta-cintāmaṇi 5.17 commentary, p. 178; Dharmasindhu p. 135"),
    "weekday": ("Monday, Wednesday, Thursday or Friday", "Muhūrta-cintāmaṇi 5.17"),
    "nakshatra": ("The Moon in Ashvini, Rohini, Mrgashira, Punarvasu, Pushya, the three Uttaras, Hasta, Citra, Svati, Anuradha, Shravana, Dhanishtha, Shatabhisha or Revati", "Dharmasindhu p. 135; Vasiṣṭha in Muhūrta-cintāmaṇi 5.17 commentary, p. 179"),
    "forenoon": ("The forenoon, sunrise to midday", "Nārada in Muhūrta-cintāmaṇi 5.17 commentary, p. 179"),
    "lagna": ("The lagna not Aries, Scorpio or Pisces", "Muhūrta-cintāmaṇi 5.17"),
    "house_10": ("The 10th house empty", "Muhūrta-cintāmaṇi 5.18; Nārada, p. 180"),
    "malefic_1_4_7": ("No malefic (Sun, Mars, Saturn, Rahu, Ketu) in the 1st, 4th or 7th", "Muhūrta-cintāmaṇi 5.18"),
    "moon_6_8": ("The Moon not in the 6th or 8th", "Muhūrta-cintāmaṇi 5.18"),
    "guru_7_8_9": ("Not Venus in the 7th, Mars in the 8th or Mercury in the 9th", "Guru in Muhūrta-cintāmaṇi 5.18 commentary, p. 180"),
    "barred_stretches": ("Bhadra on earth, the bad yogas' openings, gandanta, the sankranti and mahapata, removed as in the other lists", "Muhūrta-cintāmaṇi 1.34–35, 1.43–45, 6.41, 6.59, 6.78"),
    "vishti_yogas": ("The whole spans of Vishti (Bhadra), Vaidhriti, Vyatipata, Ganda, Atiganda, Vajra, Shula and Parigha, removed; the whole Vishti, whatever its residence, is our reading", "Dharmasindhu p. 135; Muhūrta-cintāmaṇi 5.17 commentary, p. 179"),
    "sunday": ("Excluded: Sunday, which some allow", "Dharmasindhu p. 135"),
    "bhadra": MUNDAN_RULES["bhadra"],
    "bad_yoga": MUNDAN_RULES["bad_yoga"],
    "gandanta_tithi": MUNDAN_RULES["gandanta_tithi"],
    "gandanta_nakshatra": MUNDAN_RULES["gandanta_nakshatra"],
    "gandanta_lagna": MUNDAN_RULES["gandanta_lagna"],
    "sankranti": MUNDAN_RULES["sankranti"],
    "mahapata": MUNDAN_RULES["mahapata"],
    "utpata": MUNDAN_RULES["utpata"],
    "marana": MUNDAN_RULES["marana"],
    "kana": MUNDAN_RULES["kana"],
    "dagdha": MUNDAN_RULES["dagdha"],
    "visha": MUNDAN_RULES["visha"],
    "jupiter_set": MUNDAN_RULES["jupiter_set"],
    "jupiter_old": MUNDAN_RULES["jupiter_old"],
    "jupiter_infant": MUNDAN_RULES["jupiter_infant"],
    "venus_set": MUNDAN_RULES["venus_set"],
    "venus_old": MUNDAN_RULES["venus_old"],
    "venus_infant": MUNDAN_RULES["venus_infant"],
    "infancy_old": MUNDAN_RULES["infancy_old"],
}  # fmt: skip
ANNAPRASHAN_NOTES = {
    "birthStar": "The child's birth star is allowed: Nārada and Vasiṣṭha call it good for the first rice (MC 5.17 commentary, p. 179), and the commentator calls the birth star and the 10th and 19th from it more praiseworthy (p. 180). Some exclude it (MC 5.18; DS p. 135).",
    "months": "Boys in the 6th, 8th, 10th or 12th month, or at one year; girls in the 5th, 7th, 9th or 11th (MC 5.17; DS p. 135). The time the family's own grhya-sutra names comes first, and then Jupiter's and Venus's setting is not considered (MC's commentary, p. 179).",
    "noPureDay": "When no pure day is available, a family at the prescribed month may go ahead: the saying that rites up to the first rice carry no malamasa or asta fault applies only then, and if the sixth month has the asta fault the eighth is used (DS p. 135).",
    "rite": "Vishnu, Shiva, the Moon, the Sun, the guardians of the directions, Earth, the directions and brahmanas are worshipped. On the mother's lap the child is fed payasa with curd, honey and ghee, from a gold or bronze vessel, by a hand holding gold, with mantras. Then tools, weapons, cloth and books are set before the child: what it first touches, by that it will live (DS p. 135).",
}  # fmt: skip
AKSHARARAMBH_RULES = {
    "season": ("The Sun's northern course, Capricorn to Gemini, but not in Aquarius", "Muhūrta-cintāmaṇi 5.37; Dharmasindhu p. 138"),
    "hari_sleeps": ("Not from the Devashayani Ekadashi to the Karka sankranti, while Vishnu sleeps", "Mārkaṇḍeya in Muhūrta-cintāmaṇi 5.37 commentary, p. 197"),
    "tithi": ("Tithi 2, 3, 5, 10, 11 or 12, outside the dark fortnight's last three days", "Muhūrta-cintāmaṇi 5.37; Dharmasindhu p. 138"),
    "weekday": ("Monday, Wednesday, Thursday or Friday", "Muhūrta-cintāmaṇi 5.37"),
    "nakshatra": ("The Moon in Hasta, Ashvini, Pushya, Shravana, Svati, Revati, Punarvasu, Ardra, Citra or Anuradha", "Muhūrta-cintāmaṇi 5.37; Dharmasindhu p. 138"),
    "lagna": ("Taurus, Gemini, Virgo, Sagittarius or Pisces rising", "Muhūrta-cintāmaṇi 5.37"),
    "house_8": ("The 8th house empty", "Nṛsiṃha and Śrīdhara in Muhūrta-cintāmaṇi 5.37 commentary, pp. 197–198"),
    "dakshinayana": ("The Sun's southern course, Cancer to Sagittarius: barred", "Muhūrta-cintāmaṇi 5.37; Dharmasindhu p. 138"),
    "sun_sign": ("The Sun in Aquarius: barred", "Dharmasindhu p. 138"),
    "ds_only": ("Excluded: allowed by DS only (the 13th tithi, Mrgashira, Dhanishtha, Shatabhisha, Sunday)", "Dharmasindhu p. 138"),
    "mc_only": ("Excluded: allowed by MC only (the 6th tithi)", "Muhūrta-cintāmaṇi 5.37"),
    "bhadra": MUNDAN_RULES["bhadra"],
    "bad_yoga": MUNDAN_RULES["bad_yoga"],
    "gandanta_tithi": MUNDAN_RULES["gandanta_tithi"],
    "gandanta_nakshatra": MUNDAN_RULES["gandanta_nakshatra"],
    "gandanta_lagna": MUNDAN_RULES["gandanta_lagna"],
    "sankranti": MUNDAN_RULES["sankranti"],
    "mahapata": MUNDAN_RULES["mahapata"],
    "utpata": MUNDAN_RULES["utpata"],
    "marana": MUNDAN_RULES["marana"],
    "kana": MUNDAN_RULES["kana"],
    "dagdha": MUNDAN_RULES["dagdha"],
    "visha": MUNDAN_RULES["visha"],
}  # fmt: skip
AKSHARARAMBH_NOTES = {
    "age": "The child's 5th year (MC 5.37; DS p. 138; Vasiṣṭha in MC's commentary).",
    "texts": "MC 5.37 also allows the 6th tithi, which its commentary doubts because Mārkaṇḍeya bars it (p. 197). Dharmasindhu p. 138 also allows the 13th, Mrgashira, Dhanishtha, Shatabhisha and Sunday. The list keeps what both allow; the days one text alone allows are in excluded[] (ds_only, mc_only). Neither text lists the first letters among the acts barred in an adhika month or while Jupiter or Venus is set.",
    "rite": "Ganesha, Vishnu, Sarasvati and Lakshmi are worshipped (MC 5.37). Dharmasindhu p. 138 adds one's Veda and its sutra author, the teacher, brahmanas and the nurse; the child walks three times around them and begins the letters with the pranava, and Sarasvati is invoked.",
    "vijayadashami": "The Kerala Vidyarambham on Vijayadashami is regional practice; MC and DS ask for the Sun's northern course. Dharmasindhu p. 68 has only the Navaratri Sarasvati-puja in books, invoked under Mula and sent off under Shravana.",
    "vasantaPanchami": "Vasanta Panchami fits the textual rule in tithi and season, the Sun usually still in Capricorn; vasantaPanchami marks the years its weekday and star qualify too.",
}  # fmt: skip
# vehicle-purchase.md (the lead's decisions of 15 Oct 2026): /muhurat/vehicle, /muhurat/property.
PURCHASE_NOTES = {
    "buying": "Muhūrta-cintāmaṇi 2.16 names six stars good for buying: Revati, Shatabhisha, Ashvini, Svati, Shravana and Citra. The selling stars of 2.17 (the three Purvas, Vishakha, Krttika, Ashlesha, Bharani) are barred for buying, and the commentary counts the rest middling (p. 63).",
    "vehicle": "A vehicle day needs a buying star, a riding weekday (Thursday, Monday, Sunday, Friday or Wednesday: the Vyavahāroccaya on mounting an elephant, horse or chariot, in MC's commentary on 2.18) and no rikta tithi. The rikta bar is MC 2.18's rule for horses, applied to vehicles as our reading.",
    "delivery": "delivery[] widens the stars to the Vyavahāroccaya's eleven riding stars (adding Mrgashira, Punarvasu, Hasta, Pushya and Dhanishtha), for taking delivery or a first drive.",
    "property": "No rule for buying land or a house was found in the texts read, so property days follow the general buying rule of MC 2.16. Moving in is griha-pravesh.",
    "windows": "Windows are the stretches where the muhurta finder's act (vehicle or property) raises no veto: Rahu kalam, Yamaganda, Gulika and durmuhurta, the bad yogas' opening, Bhadra on earth, the day yogas, mahapata, the Moon in the 8th from the lagna, the rikta tithis and Amavasya. Only the buyer's muhurta is checked when the seller must sell at once (MC 2.16 commentary).",
}  # fmt: skip
# vargas.md (the lead's decision of 15 Oct 2026): what BPHS (1933) PK 3.103-108 reads
# each varga for, and the six modern readings kept, labelled and uncited.
BPHS_1933 = {
    "text": "Bṛhat Parāśara Horā-śāstra (1933)",
    "edition": "With Śrīdhara’s Subodhinī Sanskrit commentary and a Hindi ṭīkā on the Uttara-khaṇḍa; edited by Giridharalāl Śarmā (Pūrva-khaṇḍa) and Govinda Śarmā (Uttara-khaṇḍa), Khemrāj Śrīkṛṣṇadās, Śrī Veṅkaṭeśvara Steam Press, Bombay, Saṃvat 1990 (1933)",
    "page": "41",
}
VARGA_USES = {
    1: ("The body.", "PK 3.103", None),
    2: ("Wealth and possessions.", "PK 3.103", None),
    3: ("Happiness from siblings.", "PK 3.104", "courage"),
    4: ("Fortune.", "PK 3.104", "property and home"),
    7: ("Children and grandchildren.", "PK 3.104", None),
    9: ("The spouse.", "PK 3.105", None),
    10: ("Great results in life.", "PK 3.105", "career"),
    12: ("The parents.", "PK 3.105", None),
    16: ("Comforts and vehicles.", "PK 3.105–106", None),
    20: ("Worship and devotion.", "PK 3.106", None),
    24: ("Learning.", "PK 3.107", None),
    27: ("Strengths and weaknesses.", "PK 3.107", None),
    30: ("Misfortunes.", "PK 3.107", None),
    40: ("Good and bad results.", "PK 3.107", "maternal legacy"),
    45: ("All matters.", "PK 3.108", "paternal legacy"),
    60: ("All matters.", "PK 3.108", "past karma"),
}
# griha-pravesh.md (the lead's decisions of 15 Oct 2026): rule ids for /muhurat/griha-pravesh.
GRIHA_PRAVESH_RULES = {
    "month": ("Magha, Phalguna, Vaishakha or Jyeshtha (amanta), with the Sun in its northern course", "Muhūrta-cintāmaṇi 13.1, p. 437; Nārada, p. 438"),
    "adhika_month": ("An adhika or kshaya month: barred", "Muhūrta-cintāmaṇi 1.47, p. 38, with the commentary, p. 40; Dharmasindhu p. 4"),
    "off_season": ("A lunar month outside MC 13.1's four (Magha, Phalguna, Vaishakha, Jyeshtha) and Nārada's middling two (Kartika, Margashirsha): barred", "Muhūrta-cintāmaṇi 13.1, p. 437, with the commentary, p. 438; 13.4, p. 442"),
    "dakshinayana": ("The Sun in its southern course, Cancer to Sagittarius: barred", "Muhūrta-cintāmaṇi 13.1, p. 437"),
    "sun_sign": ("The Sun in Cancer, Virgo or Aquarius: barred", "Guru in Muhūrta-cintāmaṇi 13.1 commentary, p. 439"),
    "jupiter_set": ("Jupiter within 11 time-degrees of the Sun: set", "Sūrya-siddhānta 9.6–7; Muhūrta-cintāmaṇi 1.46, applied by the 13.1 commentary, p. 438"),
    "jupiter_old": ("The 15 days before Jupiter sets", "Muhūrta-cintāmaṇi 5.27"),
    "jupiter_infant": ("The 15 days after Jupiter rises", "Muhūrta-cintāmaṇi 5.27"),
    "venus_set": ("Venus within 8 time-degrees of the Sun (retrograde) or 10 (direct): set", "Sūrya-siddhānta 9.6–7; Muhūrta-cintāmaṇi 1.46, applied by the 13.1 commentary, p. 438"),
    "venus_old": ("The 15 days before Venus sets in the east, or the 5 before it sets in the west", "Muhūrta-cintāmaṇi 5.27"),
    "venus_infant": ("The 3 days after Venus rises in the east, or the 10 after it rises in the west", "Muhūrta-cintāmaṇi 5.27"),
    "jupiter_sign": ("Jupiter in Leo or Capricorn: barred for its whole stay", "Muhūrta-cintāmaṇi 1.48, p. 40; 13.2, p. 440"),
    "nakshatra": ("The Moon in Citra, the three Uttaras, Rohini, Mrgashira, Anuradha, Dhanishtha, Revati or Shatabhisha", "Vasiṣṭha in Muhūrta-cintāmaṇi 13.1 commentary, p. 439"),
    "pot_chakra": ("The pot chakra: counting the Sun's star as the 1st, the Moon's star is not 1-5 or 14-21", "Muhūrta-cintāmaṇi 13.6, p. 446; Dharmasindhu p. 242"),
    "tithi": ("Not a rikta tithi (4, 9, 14) or Amavasya", "Muhūrta-cintāmaṇi 13.4, p. 442"),
    "weekday": ("Not a Sunday or Tuesday", "Muhūrta-cintāmaṇi 13.4, p. 442"),
    "lagna": ("A fixed lagna, or a dual one; never a movable one", "Muhūrta-cintāmaṇi 13.1, 13.4; Vasiṣṭha, p. 443"),
    "navamsa": ("The lagna's navamsa not movable", "Muhūrta-cintāmaṇi 13.4 commentary, p. 442"),
    "houses_4_8": ("The 4th and 8th houses empty of every planet", "Muhūrta-cintāmaṇi 13.4, p. 442, with the commentary, p. 443"),
    "moon_house": ("The Moon not in the 1st, 6th, 8th or 12th from the lagna", "Vasiṣṭha in Muhūrta-cintāmaṇi 13.3–4 commentary"),
    "bhadra": ("Bhadra on earth removed from the window, as for marriage", "Muhūrta-cintāmaṇi 1.43–45; 13.1 commentary, p. 439"),
    "bad_yoga": ("The bad yogas' opening ghatis, Parigha's first half, and Vyatipata and Vaidhriti whole, removed, as for marriage", "Muhūrta-cintāmaṇi 1.34–35; 13.1 commentary, p. 439"),
    "gandanta_tithi": ("One ghatika either side of the ends of the 5th, 10th and 15th tithis, removed", "Muhūrta-cintāmaṇi 6.41, p. 265; 13.1 commentary, p. 439"),
    "gandanta_nakshatra": ("Two ghatikas either side of Ashlesha-Magha, Jyeshtha-Mula and Revati-Ashvini, removed", "Muhūrta-cintāmaṇi 6.41, p. 265; 13.1 commentary, p. 439"),
    "gandanta_lagna": ("Half a ghatika either side of the lagna's Cancer-Leo, Scorpio-Sagittarius and Pisces-Aries boundaries, removed", "Muhūrta-cintāmaṇi 6.41, p. 265"),
    "sankranti": ("16.5 ghatikas either side of the Sun's sign change, removed (half of MC's 33 each side, our reading)", "Muhūrta-cintāmaṇi 6.78, p. 293; 13.1 commentary, p. 439"),
    "mahapata": ("Mahapata, equal declinations of the Sun and Moon, removed", "Muhūrta-cintāmaṇi 6.59; 13.1 commentary, p. 439"),
    "utpata": ("Utpata yoga, the weekday's star in the utpata column of MC 1.30 (28 nakshatras), removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "marana": ("Mrtyu yoga, the weekday's star in the mrtyu column of MC 1.30, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "kana": ("Kana yoga, the weekday's star in the kana column of MC 1.30 (Monday's is Abhijit), removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.30, p. 23"),
    "dagdha": ("Dagdha yoga, Nārada's burnt weekday-star pairs, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Nārada in Muhūrta-cintāmaṇi 1.5 commentary, p. 13"),
    "visha": ("A siddhi (amrta) weekday-star pair on its tithi, which turns it to visha, removed unless a Ravi or siddhi yoga holds then (MC 1.27, 1.42; only a Ravi yoga lifts a visha)", "Muhūrta-cintāmaṇi 1.20–21, pp. 19–20"),
    "middling_month": ("Excluded: Kartika or Margashirsha, which Nārada counts middling for house entry, outside MC 13.1's northern course", "Nārada in Muhūrta-cintāmaṇi 13.1 commentary, p. 438"),
    "infancy_old": ("Excluded: Jupiter's or Venus's infancy or old age beyond 3 days", "Muhūrta-cintāmaṇi 5.27 (5.28 gives 3 as the shortest)"),
    "krishna_after_dashami": ("The dark fortnight after Dashami: Vasiṣṭha keeps the dark fortnight only up to Dashami", "Vasiṣṭha in Muhūrta-cintāmaṇi 13.1 commentary, p. 438"),
    "saturday": ("Saturday: stability, with a fear of thieves", "Vasiṣṭha in Muhūrta-cintāmaṇi 13.4 commentary, p. 443"),
}  # fmt: skip
GRIHA_PRAVESH_NOTES = {
    "vastuPuja": "The vastu-puja and bhuta-bali are done the day before entry, under the soft, fixed, swift or movable stars or Mula (Muhūrta-cintāmaṇi 13.3a, p. 441; Dharmasindhu p. 242).",
    "door": "The door's direction sets the tithi class and the side the Sun must be on (Muhūrta-cintāmaṇi 13.5). The muhurta finder applies them when a door direction is given; this list does not.",
    "oldHouse": "An old house, or one rebuilt after fire or flood, also allows Margashirsha, Kartika and Shravana and four more stars, without the checks on Jupiter and Venus (Muhūrta-cintāmaṇi 13.2). The muhurta finder's old-house option applies it; this list is for a new house.",
    "owner": "The lagna should not be the 8th sign from the owner's birth lagna or Moon sign, and is best 3rd, 6th, 10th or 11th from them (Muhūrta-cintāmaṇi 13.1, 13.4). These need the owner's chart and are not applied here.",
    "placements": "Benefics in a trine, a kendra, or the 11th, 2nd or 3rd, and malefics in the 3rd, 6th or 11th, are preferred (Muhūrta-cintāmaṇi 13.3b). Not applied here.",
    "months": "Nārada counts Kartika and Margashirsha as middling months for house entry (Muhūrta-cintāmaṇi 13.1 commentary, p. 438); Muhūrta-cintāmaṇi's verse asks for the Sun's northern course, so this list keeps to the four best months.",
}  # fmt: skip
# attributes.md: each sign's element as its verse names it (Tajika-nilakanthi 1.2-13).
TAJIKA_NILAKANTHI = {
    "text": "Tājika-nīlakaṇṭhī",
    "edition": "Nīlakaṇṭha Daivajña (1587), with the Hindi commentary of Pt. Sītārāma, revised by Gaṇeśadatta Pāṭhaka, Bhārgava Pustakālaya, Benares, Saṃvat 1994 (1937–38)",
    "page": "2–6",
}
VIRGO_ELEMENT_NOTE = "BPHS 1933 PK 3.14, p. 14 calls Virgo prabhañjinī, 'wind'."
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
# Nirnaya-sindhu, 1918 Kalyan printing (docs/sources/observances.md); observances.py.
EKADASHI_TRADITIONS = {"smarta": "Smārta", "vaishnava": "Vaiṣṇava (Nirṇaya-sindhu)"}
EKADASHI_RULES = {
    "smarta": {
        "sunrise": ("Ekādaśī at sunrise: that day", "Nirṇaya-sindhu p. 58"),
        "ekadashi_increases": ("Ekādaśī runs long, Dvādaśī does not: householders keep the first day, ascetics the second (Skanda)", "Nirṇaya-sindhu p. 59"),
        "dvadashi_increases": ("Only Dvādaśī runs long, Ekādaśī pure: the first day (Mādhava)", "Nirṇaya-sindhu p. 60"),
        "both_increase": ("Ekādaśī and Dvādaśī both run long: everyone keeps the second day (Nārada, Mādhava)", "Nirṇaya-sindhu pp. 59–60"),
        "no_dvadashi_next_day": ("Ekādaśī at no sunrise and no Dvādaśī at the next: everyone keeps the pierced day (Skanda, Ṛṣyaśṛṅga)", "Nirṇaya-sindhu pp. 60, 62"),
        "viddha_nyuna_householders_first": ("Ekādaśī at no sunrise, Dvādaśī over before the following one: householders keep the pierced day, ascetics and those seeking liberation the next (Madana-ratna; Mādhava). Madana-ratna gives the pierced day to those with sons too", "Nirṇaya-sindhu p. 62"),
        "viddha_nyuna_dvadashi_long": ("Ekādaśī at no sunrise, Dvādaśī still current at the following one: everyone keeps the next day", "Nirṇaya-sindhu p. 60"),
    },
    "vaishnava": {
        "pure": ("No Daśamī in the 96 minutes before sunrise: that day", "Nirṇaya-sindhu p. 53"),
        "arunodaya_pierced": ("Daśamī within the 96 minutes before sunrise (aruṇodaya): the next day (Garuḍa)", "Nirṇaya-sindhu p. 53"),
        "increase": ("Ekādaśī or Dvādaśī runs long: the later day (Mādhava)", "Nirṇaya-sindhu p. 59"),
        "pierced_next_day": ("Ekādaśī at no sunrise: the pure Dvādaśī day", "Nirṇaya-sindhu pp. 53, 62–63"),
    },
}  # fmt: skip
OBSERVANCE_RULES = {
    "vrata": {
        "later_day": ("The later day, joined to the next Pratipada; never the day joined to Chaturdashi (Brahma-vaivarta). The Savitri vrata keeps the earlier day", "Nirṇaya-sindhu p. 73"),
        "only_day": ("The tithi touches no sunrise: its only day", "Nirṇaya-sindhu p. 73"),
    },
    "kojagara": {
        "kojagara_nishitha": ("Kojagara is kept on the night whose nishitha, the middle muhurta of the night, falls in the Purnima.", "Dharmasindhu p. 74; Nirṇaya-sindhu p. 285"),
        "kojagara_nishitha_both_later": ("When the Purnima covers nishitha on both nights, the later night is kept.", "Dharmasindhu p. 74; Nirṇaya-sindhu p. 285"),
        "kojagara_nishitha_neither_later": ("When the Purnima covers nishitha on neither night, the later night is kept.", "Dharmasindhu p. 74; Nirṇaya-sindhu p. 285"),
        "kojagara_some_say": ("Some keep the later night when the Purnima covers only the earlier night's nishitha and only the later night's pradosha.", "Dharmasindhu p. 74"),
    },
    "shraddha": {
        "aparahna": ("The Amavasya touches the aparahna (the last third of the daytime) of one day: that day", "Nirṇaya-sindhu pp. 81, 87"),
        "aparahna_both_kutapa": ("It touches both afternoons: the day whose kutapa (the 8th of the 15 day muhurtas) it covers (Mādhava)", "Nirṇaya-sindhu p. 87"),
        "kutapa_one_day": ("Neither afternoon: the day whose kutapa it covers", "Nirṇaya-sindhu pp. 86–87"),
        "kutapa_more": ("Kutapa partly covered on both days: the day with more", "Nirṇaya-sindhu p. 87"),
        "kutapa_tie_kshaya_earlier": ("Equal on both days and the Amavasya touches no sunrise: the earlier day (Pracetas)", "Nirṇaya-sindhu p. 87"),
        "kutapa_tie_later": ("Equal on both days, or covered on both: the later day (Pracetas)", "Nirṇaya-sindhu p. 87"),
        "kutapa_none_later": ("Neither afternoon nor kutapa touched: the later day (our fallback; not seen in practice)", None),
    },
    "pradosha": {
        "covers_pradosha": ("The day whose whole pradosha (three muhurtas after sunset) the Trayodashi covers", "Nirṇaya-sindhu p. 72, footnote (Brahmottara-khaṇḍa)"),
        "both_covered_later": ("It covers pradosha on both days: the later day; Mayūkha (after Sumantu) takes the earlier", "Nirṇaya-sindhu p. 72, footnote"),
        "neither_covered_later": ("It reaches neither day's pradosha: the later day; Mayūkha (after Sumantu) takes the earlier", "Nirṇaya-sindhu p. 72, footnote"),
        "equal_touch_later": ("It touches both pradoshas equally: the later day; Mayūkha takes the earlier", "Nirṇaya-sindhu p. 72, footnote"),
        "more_pradosha": ("It covers part of pradosha, on one evening only or unequally on both: the day with more of it (the other opinion recorded there)", "Nirṇaya-sindhu p. 72, footnote"),
    },
}  # fmt: skip
# observances.md s9 (provisional: the lead's decision 3)
OBSERVANCE_RULES["parana"] = {
    "morning": (
        "Within the first three muhurtas after sunrise, once Hari-vasara (Dvadashi's first quarter) is over and before Dvadashi ends (the majority)",
        "Dharmasindhu p. 19; Nirṇaya-sindhu p. 71",
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
    "(Dharmasindhu p. 19). In a difficulty, water counts as breaking it (Devala, Nirṇaya-sindhu "
    "p. 71). With a short Dvadashi the morning and midday rites move to dawn so the meal falls "
    "inside it (NS p. 70). Nirṇaya-sindhu's own teachers prefer the afternoon even when the "
    "morning is open (p. 71)."
)
# observances.md s8 (provisional: the lead's decision 8)
OBSERVANCE_RULES["mahalaya"] = {
    "one_day": (
        "The tithi holds the afternoon (the 10th-12th day muhurtas, our reading) of one day only: that day",
        "Nirṇaya-sindhu p. 718",
    ),
    "both_earlier": (
        "It holds both afternoons, fully or equally in part: the earlier day",
        "Nirṇaya-sindhu p. 718",
    ),
    "more": (
        "It holds part of both afternoons, unequally: the day with more (Marīci)",
        "Nirṇaya-sindhu p. 718",
    ),
    "neither_three_muhurtas_earlier": (
        "Neither afternoon, but current three muhurtas before the first day's sunset: the earlier day (Sumantu)",
        "Nirṇaya-sindhu p. 719",
    ),
    "neither_later": (
        "Neither afternoon: the later day, whose kutapa it holds (Gobhila)",
        "Nirṇaya-sindhu p. 719",
    ),
}
OBSERVANCE_RULES["ekoddishta"] = {
    "one_day": (
        "The Chaturdashi holds the midday (kutapa to rauhina, the 8th-9th day muhurtas) of one day only: that day",
        "Nirṇaya-sindhu p. 718",
    ),
    "both_earlier": (
        "Both middays, fully or equally in part: the earlier day",
        "Nirṇaya-sindhu p. 718",
    ),
    "more": ("Both, unequally: the day with more", "Nirṇaya-sindhu p. 718"),
    "neither_earlier": (
        "Neither midday: the earlier day; the Gauda later-day view is rejected",
        "Nirṇaya-sindhu p. 718",
    ),
}
OBSERVANCE_RULES["matamaha"] = {
    "one_day": (
        "The Pratipada current at sangava (the 4th-6th day muhurtas, our reading) of one day only: that day",
        "Nirṇaya-sindhu p. 239 (Nirṇaya-dīpa)",
    ),
    "both_earlier": ("At both sangavas, fully or equally: the earlier day (our reading)", None),
    "more": ("At both, unequally: the day with more (our reading)", None),
    "neither_later": ("At neither: the later day (our fallback)", None),
}
PITRU_PAKSHA_NOTES = {
    "fortnight": "The dark fortnight ending amanta Bhadrapada (purnimanta Ashvina), the fifth from the Ashadha full moon; NS counts its sixteen days to Ashvina shukla Pratipada (p. 215). Each tithi's day is for those who died on that tithi.",
    "windows": "Day muhurtas are fifteenths of sunrise to sunset. The afternoon is the 10th-12th (the fourth fifth of the day: our reading, from NS p. 717's five-part midday); kutapa to rauhina the 8th-9th (Gautama, p. 718); sangava the 4th-6th (our reading).",
    "navami": "Navami: for all mothers, stepmothers too, even by a son whose father lives (NS p. 229). Popularly 'Avidhava Navami': NS feeds a suvasini with the brahmanas for a woman who died before her husband (p. 231) but does not limit the day to such women, and the name was not found.",
    "dvadashi": "Dvadashi: for renunciants (Vāyu-purāṇa via the Pṛthvīcandrodaya, NS p. 232).",
    "trayodashi": "Trayodashi: dear to the ancestors, more so with Magha (Candrikā, NS p. 232); obligatory, kept even in an intercalary month (pp. 233–234). A man with children offers no pindas on a Magha-joined Trayodashi (Bṛhat-Parāśara, p. 234). With the Moon in Magha and the Sun in Hasta it is gaja-cchaya (p. 233).",
    "chaturdashi": "Chaturdashi: only for those killed by weapons, falls, lightning, water, poison, fire or animals, not for deaths in childbirth (NS p. 235). It is an ekoddishta (p. 236), so the midday decides; variantDate is the afternoon table's day where it differs.",
    "amavasya": "Amavasya: the last day of the fortnight. With the Moon and the Sun both in Hasta it is also gaja-cchaya (Yama via Aparārka, NS p. 238). 'Sarva-pitr' was not found as a name.",
    "bharani": "Bharani in the pitr-paksha is 'great': a shraddha then equals one at Gaya (Mātsya via the Pṛthvīcandrodaya, NS p. 225); popularly Maha-bharani. The texts read do not fix the hour; the day whose afternoon holds the star is shown.",
    "magha": "Magha is a shraddha occasion of its own (Vasiṣṭha, Yājñavalkya; NS p. 233). The day whose afternoon holds the star is shown.",
    "matamaha": "Ashvina shukla Pratipada: the maternal grandfather's shraddha by a daughter's son, even newborn (Hemādri's Saṅgraha, NS p. 239). The Nirṇaya-dīpa takes the Pratipada current at sangava, a verse whose source NS doubts. Not in an intercalary month.",
    "purnima": "A Purnima shraddha on the Bhadrapada full moon is popular practice; the texts read give it no day, so none is shown.",
    "variant": "Mādhava and the Pṛthvīcandrodaya take the earlier day in kshaya and the later in vrddhi, of the following tithi, when the afternoon is covered on both days (NS pp. 719–720). Not computed: the comparison it rests on is not defined on the pages read.",
}  # fmt: skip
OBSERVANCE_RULES["sankranti"] = {
    "day": ("A day ingress: that day, the class's window (DS p. 2) within daylight", "Dharmasindhu pp. 2–3; Nirṇaya-sindhu pp. 5, 9"),
    "day_sunset_edge": ("Within two ghatis before sunset, an after-window turns before the ingress", "Dharmasindhu p. 2; Nirṇaya-sindhu p. 6"),
    "day_sunrise_edge": ("Within two ghatis after sunrise, a before-window turns after the ingress", "Dharmasindhu p. 2; Nirṇaya-sindhu p. 6"),
    "night_before_midnight": ("A night ingress before midnight: the previous day, midday to sunset, best its last five nadis", "Dharmasindhu pp. 2, 85; Nirṇaya-sindhu pp. 9–10, 161"),
    "night_after_midnight": ("A night ingress after midnight: the next day, sunrise to midday, best its first five nadis", "Dharmasindhu pp. 2, 85; Nirṇaya-sindhu pp. 9–10"),
    "night_midnight_both": ("An ingress at midnight (the two-ghati nishitha): both half-days", "Dharmasindhu p. 2; Nirṇaya-sindhu p. 10"),
    "makara_night_next_day": ("Makara at night, at any hour: the next day, its forenoon, best the five nadis after sunrise (the southern usage)", "Dharmasindhu p. 85; Nirṇaya-sindhu p. 326"),
    "karka_night_previous_day": ("Karka at night, before or after midnight: the previous day, after its midday (the southern usage)", "Dharmasindhu p. 41; Nirṇaya-sindhu p. 161"),
}  # fmt: skip
SANKRANTI_NOTES = {
    "windows": "DS p. 2's windows, in ghatis of 24 minutes: Mesha and Tula 15 before and 15 after (NS and DS's Caitra passage: 10 and 10); Vrshabha, Simha, Vrshcika and Kumbha 16 before; Mithuna, Kanya, Dhanus and Mina 16 after; Karka 30 before; Makara 40 after (Hemādri; Mādhava gives 20). Clipped to daylight, our reading of DS p. 3: the bath is by day even after a night ingress.",
    "best": "best is the five nadis DS p. 85 and the Skanda (NS pp. 161, 326) name for a night ingress. For a day ingress it is the five nearest the ingress, our reading of 'the nadis nearest the ingress are the most meritorious' (DS p. 85). Neither text uses the term maha-punyakala.",
    "variants": "Baudhāyana (NS p. 327) holds both days meritorious for a night Makara, the usage of Gujarat, the east and the north; Hemādri, Aparārka and others split a night Makara or Karka at midnight like the other ten (NS pp. 161, 326–327).",
    "twilight": "Jyotisha texts count a Makara ingress within three ghatis after sunset for the day just ended, and a Karka within three ghatis before sunrise for the next day (DS pp. 2, 41, 86); DS notes this is not found throughout the dharmashastra works. jyotishaTwilight marks the years it applies.",
    "sayana": "Both texts also count the ingress shifted by the ayanamsha, the tropical ingress (NS pp. 7–8; DS p. 2, about 21 days earlier in 1790). sayana gives it; it is never the date here.",
    "rites": "A bath and gifts at every ingress, each with its own gift (Viśvāmitra via Hemādri, NS pp. 6–7; DS p. 2): for Makara firewood and fire. At the ayanas and vishuvas a fast before the bath, not for a householder with a son, and a shraddha without pindas, obligatory at the ayanas. At Makara the bath is obligatory, with sesame throughout: sesame gifts, lamps of sesame oil, sesame in the bath and in food (DS p. 86). Auspicious acts are avoided 16 ghatis either side of any ingress, and the ayana day and the day after (DS pp. 2, 86).",
}  # fmt: skip
OBSERVANCE_RULES["sankashti"] = {
    "moonrise": ("The krishna Chaturthi current at moonrise", "Nirṇaya-sindhu p. 47; Vīramitrodaya, Samaya-prakāśa, p. 38"),
    "both_earlier": ("Current at both moonrises: the earlier day, joined with Trtiya (some, in NS); others take the later day", "Nirṇaya-sindhu p. 47"),
    "neither_later": ("Current at neither moonrise: the later day", "Nirṇaya-sindhu p. 47"),
}  # fmt: skip
FESTIVAL_RULES = {
    "dipavali": {
        "pradosha": ("The Amavasya current at pradosha", "Nirṇaya-sindhu pp. 299–300"),
        "danda_next_night_later": ("It touches at least one danda (24 minutes) of the next night: the later day (Tithi-tattva)", "Nirṇaya-sindhu p. 300"),
        "neither_later": ("Current at neither pradosha: the later day (our fallback)", None),
        "dhanteras_pradosha": ("Dhanteras: the dark Trayodashi current at pradosha, when the lamp for Yama is set outside", "Nirṇaya-sindhu p. 294; Dharmasindhu p. 76"),
        "dhanteras_both_later": ("The Trayodashi at pradosha on both days: the later day, as a dark Trayodashi is taken on the later day", "Dharmasindhu p. 20"),
        "dhanteras_neither_later": ("The Trayodashi at pradosha on neither day: the later day", "Dharmasindhu p. 20"),
        "naraka_moonrise": ("The oil bath is taken at the dawn whose pre-dawn moonrise falls in the Caturdashi.", "Dharmasindhu p. 76; Nirṇaya-sindhu p. 294"),
        "naraka_moonrise_both_earlier": ("When the Caturdashi is current at the pre-dawn moonrise on both days, the bath is taken on the earlier day.", "Dharmasindhu p. 76; Nirṇaya-sindhu p. 295"),
        "naraka_lamps_divodasiya": ("With the bath on the second day, the Divodāsīya gives the lamps at the earlier evening's pradosha, while the Caturdashi is current.", "Nirṇaya-sindhu p. 297"),
        "naraka_began_before_sunrise": ("When the Caturdashi begins between the first day's moonrise and sunrise, at least a ghatika before sunrise, and ends before the second day's moonrise, the bath is taken that first dawn, from its start to sunrise.", "Dharmasindhu pp. 76–77"),
        "naraka_later_moonrise": ("When the Caturdashi touches the first day only at sunrise, beginning less than a ghatika before it, and ends before the second day's moonrise, the bath is taken on the second day, at moonrise.", "Dharmasindhu p. 77"),
        "naraka_no_sunrise_next_dawn": ("When the Caturdashi holds no sunrise, the bath is taken at the next dawn, after the Caturdashi has ended.", "Dharmasindhu p. 77"),
        "govardhan_nine_muhurtas": ("Govardhana-puja and Bali-pratipada: the Pratipada at sunrise lasting nine muhurtas or more after it puts every rite on that day (ten in the text; nine to ten our reading)", "Dharmasindhu p. 78"),
        "govardhan_earlier": ("Lasting under nine muhurtas: Bali's worship, the cow play, the Govardhana-puja and the margapali on the Amavasya-joined day before; the bath, new clothes and nirajana stay on the sunrise day (bathDate)", "Dharmasindhu p. 78"),
        "govardhan_no_sunrise_earlier": ("A Pratipada touching no sunrise: the day it begins, joined with the Amavasya (our reading of DS's rule)", "Dharmasindhu p. 78"),
        "bhai_dooj_earlier_alone": ("Bhai Dooj (Yama-dvitiya): the Dvitiya covers the afternoon on the earlier day alone: that day", "Dharmasindhu p. 79"),
        "bhai_dooj_later": ("Otherwise, the afternoon covered on both days or on neither: the later day", "Dharmasindhu p. 79"),
    },
    "shivaratri": {
        "midnight_both_pradosha_later": ("Midnight on both days, pradosha only on the later: the later day (Mādhava, endorsed by NS); Hemādri takes the first", "Nirṇaya-sindhu p. 336"),
        "midnight_both_pradosha": ("Midnight on both days, pradosha only on the first: the first day", "Nirṇaya-sindhu p. 337"),
        "midnight_both_first": ("Midnight on both days, pradosha on both or neither: the first day (Hemādri)", "Nirṇaya-sindhu p. 335"),
        "by_midnight": ("Midnight decides: the day with (more of) it, so the first when it has all of midnight (Īśāna-saṃhitā)", "Nirṇaya-sindhu pp. 336–337"),
        "by_pradosha": ("No midnight on either day: the day with pradosha", "Nirṇaya-sindhu p. 337"),
        "neither_later": ("Neither window on either day: the later day (our fallback)", None),
    },
    "ganesha-chaturthi": {
        "next_day_midday": ("The Chaturthi reaches the next day's midday: the next day", "Nirṇaya-sindhu pp. 47, 198 (Bṛhaspati)"),
        "trtiya_joined_earlier": ("Otherwise the earlier day, joined with Trtiya", "Nirṇaya-sindhu pp. 47, 198"),
    },
    "raksha-bandhan": {
        "udaya_three_muhurtas": ("The Purnima lasts more than three muhurtas after the later sunrise: that day, in the afternoon or at pradosha, free of Bhadra", "Dharmasindhu p. 49"),
        "earlier_pradosha": ("Otherwise the earlier day, at pradosha or about then, free of Bhadra", "Dharmasindhu p. 49"),
    },
    "janmashtami": {
        "first_only": ("The Ashtami at midnight on the first day only: the first", "Nirṇaya-sindhu pp. 189–190"),
        "second_only": ("At midnight on the second day only: the second", "Nirṇaya-sindhu pp. 189–190"),
        "both_later": ("At midnight on both days, equally: the second; the Ashtami joined with Saptami is avoided (Brahma-vaivarta)", "Nirṇaya-sindhu p. 190"),
        "neither_later": ("At midnight on neither day: the second", "Nirṇaya-sindhu p. 190"),
        "more": ("Partly on both days, unequally: the day with more of it", "Nirṇaya-sindhu p. 190"),
        "split_rohini_day": ("The Ashtami holds the first midnight and meets Rohini on the second day: one observance, on the Rohini day (Mādhava). Nirṇaya-sindhu keeps two fasts, the first day being its Janmashtami (variantDate); Hemādri keeps the first", "Dharmasindhu pp. 50–51; Nirṇaya-sindhu pp. 191–192"),
    },
    "jayanti": {
        "first": ("The Ashtami and Rohini together at midnight on the first day only: the first, even when joined with Saptami (Padma)", "Nirṇaya-sindhu p. 190"),
        "second": ("Together at midnight on the second day only: the second", "Nirṇaya-sindhu p. 190"),
        "both_later": ("Together at midnight on both days: the second (Brahma-vaivarta)", "Nirṇaya-sindhu pp. 190–191"),
        "split_later": ("The Ashtami at the first midnight, Rohini at the second: the second, for the Jayanti joining (Mādhava); Hemādri takes the first", "Nirṇaya-sindhu p. 191"),
    },
    "sharad-navaratri": {
        "pratipada_at_sunrise": ("The Pratipada current at sunrise, best lasting three muhurtas after it, then two, by some texts one; never the one joined with Amavasya", "Dharmasindhu p. 65; Nirṇaya-sindhu pp. 240–241"),
        "full_day_first": ("The Pratipada fills a whole day and runs into the next: the first, as complete", "Dharmasindhu p. 65"),
        "under_one_muhurta_amavasya_joined": ("The Pratipada lasts under a muhurta after sunrise: the day joined with Amavasya", "Dharmasindhu p. 65"),
        "no_sunrise_amavasya_joined": ("The Pratipada touches no sunrise: its only day, joined with Amavasya", "Dharmasindhu p. 65"),
    },
    "chaitra-navaratri": {
        "sunrise_one_day": ("The new year (Gudi Padwa, Ugadi): the Caitra shukla Pratipada at one sunrise: that day", "Dharmasindhu p. 31"),
        "both_earlier": ("The Pratipada at sunrise on both days: the earlier", "Dharmasindhu p. 31"),
        "neither_earlier": ("The Pratipada at neither sunrise: the earlier, the day it falls on", "Dharmasindhu p. 31"),
    },
    "karva-chauth": {
        "moonrise": ("Karaka-caturthi: the dark Caturthi current at moonrise", "Nirṇaya-sindhu p. 293; Dharmasindhu p. 76"),
        "both_earlier": ("Current at both moonrises: the earlier day, joined with the Trtiya; the worship is set at moonrise", "Nirṇaya-sindhu p. 293; Dharmasindhu p. 9"),
        "neither_later": ("Current at neither moonrise: the later day, as for Sankashti", "Dharmasindhu pp. 9, 76"),
    },
    "tulsi-vivah": {
        "parana_day_early_night": ("Joined to the Prabodhotsava on the parana day of the Prabodhini Ekadashi, in the early night (pradosha, our reading); the day after the Smarta fast", "Dharmasindhu pp. 81–82"),
    },
    "tripurotsava": {
        "tripura_pradosha": ("The Kartika Purnima current at dusk (pradosha) on one day: that day", "Nirṇaya-sindhu p. 312; Dharmasindhu p. 84"),
        "tripura_both_later": ("Current at dusk on both days: the later, as the Kartika Purnima is taken on the later day", "Nirṇaya-sindhu p. 311"),
        "tripura_neither_later": ("Current at dusk on neither day: the later", "Nirṇaya-sindhu p. 311"),
    },
    "vasanta-panchami": {
        "forenoon_later_alone": ("The Panchami covers the forenoon on the later day alone: the later day", "Dharmasindhu p. 89"),
        "earlier": ("Otherwise the earlier day, joined with the Caturthi", "Dharmasindhu pp. 9, 89"),
        "both_earlier": ("The forenoon covered on both days: the earlier", "Dharmasindhu p. 89"),
    },
    "ratha-saptami": {
        "arunodaya": ("The Saptami covering arunodaya, the four ghatikas before sunrise", "Nirṇaya-sindhu p. 329; Dharmasindhu p. 89"),
        "arunodaya_both_earlier": ("Covering arunodaya on both days: the earlier", "Dharmasindhu p. 89; Vratarāja f. 115"),
        "shashthi_joined_first_day": ("A short Saptami ending before the next arunodaya: the first day, bathed at its arunodaya in the Shashthi (NS p. 330); one touching neither arunodaya goes there too (our reading)", "Nirṇaya-sindhu p. 330; Dharmasindhu p. 89"),
    },
    "bhishma-ashtami": {
        "one_day": ("The Ashtami covers midday on one day only: that day", "Dharmasindhu p. 90; Nirṇaya-sindhu p. 718"),
        "both_earlier": ("Covered on both days, fully or equally: the earlier", "Nirṇaya-sindhu p. 718"),
        "more": ("Covered unequally on both days: the day with more", "Nirṇaya-sindhu p. 718"),
        "neither_earlier": ("Covered on neither day: the earlier", "Nirṇaya-sindhu p. 718"),
    },
    "kalashtami": {
        "midday": ("Kalashtami: the Ashtami covering midday (the 3rd fifth) on one day: that day", "Nirṇaya-sindhu p. 313"),
        "midday_both_earlier": ("Covering midday on both days, wholly or in part: the earlier", "Nirṇaya-sindhu p. 313"),
        "midday_neither_sunrise_day": ("Covering neither midday: the day whose sunrise it holds (our reading)", None),
        "pradosha_only_earlier_ds": ("The earlier day holding the Ashtami only at pradosha and the later only at midday: the pradosha day, as Dharmasindhu judges from the conduct of many learned people", "Dharmasindhu p. 84"),
        "vigil_one_night": ("The night vigil alone: the Ashtami touching one day's night (sunset to sunrise): that day", "Nirṇaya-sindhu p. 312"),
        "vigil_both_later": ("Touching both nights in part: the later", "Nirṇaya-sindhu p. 313"),
        "vigil_whole_night": ("Covering one night wholly and only touching the other: the wholly covered one (our reading)", "Nirṇaya-sindhu pp. 312–313"),
    },
    "dattatreya-jayanti": {
        "pradosha": ("The Margashirsha Purnima covering pradosha on one day: that day", "Nirṇaya-sindhu p. 315; Dharmasindhu p. 84"),
        "pradosha_both_later": ("Covering pradosha on both days: the later (our reading, by the Purnima rule of NS p. 73)", "Nirṇaya-sindhu pp. 73, 315"),
        "pradosha_neither_later": ("Covering neither pradosha: the later (our reading)", "Nirṇaya-sindhu pp. 73, 315"),
    },
    "ganesha-jayanti": {
        "next_day_midday": ("The Vinayaka-vrata: the Caturthi reaches the next day's midday: the next day, as for Bhadrapada", "Dharmasindhu p. 89; Nirṇaya-sindhu pp. 47, 198"),
        "trtiya_joined_earlier": ("Otherwise the earlier day, joined with the Trtiya", "Dharmasindhu p. 89"),
        "vow_pradosha": ("The Tila or Varada night vow: the Caturthi covering pradosha on one day: that day", "Dharmasindhu p. 89; Nirṇaya-sindhu p. 329; Vratarāja f. 82"),
        "vow_pradosha_both_earlier": ("Covering pradosha on both days: the earlier, Trtiya-joined day (DS p. 9's Caturthi rule, our reading)", "Dharmasindhu pp. 9, 89"),
        "vow_pradosha_neither_later": ("Covering neither pradosha: the later day (our reading)", "Dharmasindhu p. 89"),
    },
    "holashtak": {
        "holashtak_period": ("The eight days from the Phalguna shukla Ashtami to the Purnima, avoided for marriage and auspicious acts only on the Beas, Ravi and Sutlej and at Pushkar", "Muhūrta-cintāmaṇi 1.40, p. 33, with the commentary, p. 34, which quotes the Śīghrabodha"),
    },
    "akshaya-tritiya": {
        "forenoon": ("The Vaishakha shukla Tritiya covering the forenoon (sunrise to midday) on one day: that day", "Nirṇaya-sindhu p. 134; Dharmasindhu p. 36; Vratarāja f. 43"),
        "forenoon_both_three_muhurtas": ("Covering the forenoon on both days, the Tritiya lasting more than three day-muhurtas into the later: the later (DS); NS and VR take the later in any case (variantDate)", "Dharmasindhu p. 36; Nirṇaya-sindhu p. 134"),
        "forenoon_both_earlier": ("Covering the forenoon on both days, the Tritiya lasting three day-muhurtas or less into the later: the earlier (DS); NS and VR take the later (variantDate)", "Dharmasindhu p. 36; Nirṇaya-sindhu p. 134"),
        "forenoon_neither_later": ("Covering neither forenoon: the later, Caturthi-joined day, which NS prefers (our reading)", "Nirṇaya-sindhu p. 134"),
    },
    "parashurama-jayanti": {
        "first_watch_earlier_only": ("The Tritiya covering the night's first watch on the earlier day only: that day", "Dharmasindhu p. 37"),
        "first_watch_later": ("Otherwise, covered on both days or neither: the later (the first watch is a quarter of the night, our reading)", "Dharmasindhu p. 37; Vratarāja f. 43"),
    },
    "guru-purnima": {
        "three_muhurtas_later": ("The Ashadha Purnima lasts three muhurtas or more after the later sunrise: that day", "Nirṇaya-sindhu p. 160; Dharmasindhu p. 43"),
        "caturdashi_joined_earlier": ("Otherwise the earlier, Caturdashi-joined day", "Dharmasindhu pp. 20, 43"),
    },
    "vat-savitri": {
        "caturdashi_joined": ("The Purnima (or Amavasya) runs more than three muhurtas before the Caturdashi-joined day's sunset: that day, the exception to the later-day rule for these fasts", "Nirṇaya-sindhu pp. 147–148; Dharmasindhu p. 41"),
        "under_three_muhurtas_later": ("It runs three muhurtas or less before that sunset: the later day", "Dharmasindhu p. 41"),
        "puja_only_later": ("The Caturdashi lasts 18 nadis (7 h 12 min) or more after the Caturdashi-joined day's sunrise: the puja on the later day, the three-night fast kept on the earlier (fastDate); the Amavasya form by NS p. 148's 'the same holds for the Amavasya' (our reading)", "Dharmasindhu p. 41; Nirṇaya-sindhu p. 148"),
    },
    "ganga-dussehra": {
        "forenoon": ("The Jyeshtha shukla Dashami in the forenoon (sunrise to midday) of one day only: that day", "Dharmasindhu p. 38"),
        "forenoon_both_more_yogas": ("In both forenoons: the day with more of the ten yogas, counted where they meet the Dashami in the forenoon (our reading of 'in the forenoon')", "Nirṇaya-sindhu p. 144; Dharmasindhu p. 38"),
        "forenoon_both_tie_vyatipata": ("As many yogas on both days: the day with Vyatipata, which Dharmasindhu names chief with the Dashami (our reading; the texts give no tie rule)", "Dharmasindhu p. 38"),
        "forenoon_both_tie_sunrise": ("As many yogas, and Vyatipata on both days or neither: the day with the Dashami at sunrise (our reading)", None),
    },
    "rath-yatra": {
        "sunrise_tritiya_joined": ("The Ashadha shukla Dvitiya at sunrise, Trtiya-joined, as the paired-tithi rule pairs them (our reading; the texts give no rule for a Dvitiya spanning two days)", "Nirṇaya-sindhu p. 149"),
        "two_sunrises_first": ("The Dvitiya at two sunrises: the first (our reading, matched to prevailing practice)", "Nirṇaya-sindhu p. 149"),
        "no_sunrise_day_it_falls_on": ("The Dvitiya at no sunrise: the day it falls on (our reading)", "Nirṇaya-sindhu p. 149"),
    },
    "sawan-somvar": {
        "shravana_monday": ("A Monday whose sunrise falls in Shravana: the Monday vow, a fast for those able, otherwise one meal at night", "Dharmasindhu p. 44"),
    },
    "hariyali-teej": {
        "sunrise_caturthi_joined": ("The Tritiya at sunrise, Caturthi-joined: that day, even with a muhurta or less of Tritiya after sunrise", "Nirṇaya-sindhu p. 197; Dharmasindhu p. 55"),
        "two_sunrises_later": ("The Tritiya at two sunrises: the later, Caturthi-joined day, even when it fills the earlier", "Dharmasindhu p. 55"),
        "kshaya_dvitiya_joined": ("The Tritiya at no sunrise: the day it runs, Dvitiya-joined", "Dharmasindhu p. 55"),
    },
    "kajari-teej": {
        "sunrise_caturthi_joined": ("The Tritiya at sunrise, Caturthi-joined: that day, even with a muhurta or less of Tritiya after sunrise", "Nirṇaya-sindhu p. 197; Dharmasindhu p. 55"),
        "two_sunrises_later": ("The Tritiya at two sunrises: the later, Caturthi-joined day, even when it fills the earlier", "Dharmasindhu p. 55"),
        "kshaya_dvitiya_joined": ("The Tritiya at no sunrise: the day it runs, Dvitiya-joined", "Dharmasindhu p. 55"),
    },
    "hartalika-teej": {
        "sunrise_caturthi_joined": ("The Tritiya at sunrise, Caturthi-joined: that day, even with a muhurta or less of Tritiya after sunrise", "Nirṇaya-sindhu p. 197; Dharmasindhu p. 55"),
        "two_sunrises_later": ("The Tritiya at two sunrises: the later, Caturthi-joined day, even when it fills the earlier", "Dharmasindhu p. 55"),
        "kshaya_dvitiya_joined": ("The Tritiya at no sunrise: the day it runs, Dvitiya-joined", "Dharmasindhu p. 55"),
    },
    "nag-panchami": {
        "three_muhurtas_later": ("The Panchami lasts three muhurtas or more after the later sunrise: the later, Shashthi-joined day", "Dharmasindhu p. 44; Nirṇaya-sindhu p. 164"),
        "both_short_earlier": ("Under three muhurtas after the later sunrise, the earlier day's Caturthi lasting three or less after its sunrise: the earlier day", "Dharmasindhu p. 44"),
        "long_caturthi_later": ("Two to three muhurtas after the later sunrise, the earlier day's Caturthi lasting more than three: the later day", "Dharmasindhu p. 44"),
        "under_two_muhurtas_earlier": ("Under two muhurtas after the later sunrise, with a Caturthi of more than three before: the earlier day (Dharmasindhu rejects a Panchami of one muhurta; under two is our reading)", "Dharmasindhu p. 44"),
        "no_sunrise_day_it_runs": ("The Panchami at no sunrise: the day it runs", "Dharmasindhu p. 44"),
        "two_sunrises_later": ("The Panchami at two sunrises: the later", "Nirṇaya-sindhu p. 164"),
    },
    "rishi-panchami": {
        "midday": ("The Bhadrapada shukla Panchami at midday (the 3rd fifth of the daytime) on one day only: that day", "Dharmasindhu p. 55"),
        "midday_both_earlier": ("At midday on both days: the earlier", "Dharmasindhu p. 55"),
        "midday_neither_earlier": ("At midday on neither day: the earlier", "Dharmasindhu p. 55"),
    },
    "anant-chaturdashi": {
        "sunrise_three_muhurtas": ("The Caturdashi at sunrise, lasting three muhurtas or more after it: that day (the main rule)", "Dharmasindhu p. 58"),
        "sunrise_two_muhurtas": ("At sunrise, lasting two to three muhurtas after it: that day (the secondary rule)", "Dharmasindhu p. 58"),
        "under_two_muhurtas_earlier": ("At sunrise, lasting under two muhurtas after it: the earlier day", "Dharmasindhu p. 58"),
        "sunrise_both_earlier": ("At sunrise on both days: the earlier, as the complete one", "Dharmasindhu p. 58"),
        "no_sunrise_only_day": ("The Caturdashi at no sunrise: its only day (our reading)", None),
    },
    "chhath": {
        "sunrise_holds_shashthi": ("Chhath: the evening arghya on the first day whose sunrise falls within the Kartika shukla Shashthi (popular practice; no text read gives the day)", None),
        "two_sunsets_later": ("Both sunsets within the Shashthi: the later, on the day whose sunrise holds it, so that Kharna, the evening arghya and the morning arghya each keep their own tithi (popular practice; no text read gives the day; our reading)", None),
        "sunset_in_shashthi": ("No sunrise within the Shashthi: the day whose sunset falls in it (popular practice; no text read gives the day)", None),
    },
    "chaiti-chhath": {
        "sunrise_holds_shashthi": ("Chaiti Chhath, the spring Chhath: the evening arghya on the first day whose sunrise falls within the Caitra shukla Shashthi, by the Kartika Chhath's rule (popular practice; no text read gives the day)", None),
        "two_sunsets_later": ("Both sunsets within the Shashthi: the later, on the day whose sunrise holds it, so that Kharna, the evening arghya and the morning arghya each keep their own tithi (popular practice; no text read gives the day; our reading)", None),
        "sunset_in_shashthi": ("No sunrise within the Shashthi: the day whose sunset falls in it (popular practice; no text read gives the day)", None),
    },
    "hanuman-jayanti": {
        "purnima_vrata_day": ("Hanuman Jayanti: the Caitra Purnima, on the site's Purnima-vrata day, the main northern date (popular practice; no text read gives the day)", None),
    },
    "radhashtami": {
        "midday_one_day": ("Radhashtami: the Bhadrapada shukla Ashtami covering midday (the 3rd fifth) on one day: that day (popular practice; no text read gives the day)", None),
        "midday_both_later": ("Covering both middays: the later, whose sunrise holds the Ashtami (popular practice; no text read gives the day)", None),
        "midday_neither_later": ("Covering neither midday: the later, whose sunrise holds the Ashtami (popular practice; no text read gives the day)", None),
    },
    "onam": {
        "sunrise_six_nadikas": ("Onam: the Chingam day (the Sun in sidereal Simha at sunrise) whose sunrise falls in Shravana with 6 nadikas (2 h 24 min) of it left; when two sunrises pass, the later (popular practice; no text read gives the day; our reading)", None),
        "short_day_before": ("Less than 6 nadikas of Shravana after the only sunrise in it: the day before, which holds most of it (popular practice; no text read gives the day)", None),
        "no_sunrise_day_it_falls_in": ("Shravana at no sunrise: the day it falls in (popular practice; no text read gives the day; our reading)", None),
        "atham_sunrise_six_nadikas": ("Atham, the opening: the last day before that Onam whose sunrise falls in Hasta with 6 nadikas of it left; it may fall in late Karkataka (our reading; popular practice)", None),
        "atham_short_day_before": ("Less than 6 nadikas of Hasta after the only sunrise in it: the day before (our reading; popular practice)", None),
        "atham_no_sunrise_day_it_falls_in": ("Hasta at no sunrise: the day it falls in (our reading; popular practice)", None),
    },
    "vishwakarma-puja": {
        "kanya_sankranti_punyakala": ("Vishwakarma Puja: the day of the Kanya sankranti's punyakala, as /observances/sankranti computes it (popular practice; no text read gives the day)", None),
    },
    "karthigai-deepam": {
        "krittika_at_sunset": ("Karthigai Deepam is kept on the day in the solar month Karttikai whose sunset falls in Krittika, computed at Tiruvannamalai for every city (popular practice; our rule, drawn from the days observed)", None),
        "two_sunsets_sunrise_day": ("When Krittika holds both sunsets, the day that also has it at sunrise is taken, and the other day is the variant (our reading; popular practice)", None),
        "no_sunset_evening_it_begins": ("When Krittika holds neither sunset, the evening on which it begins is taken, and the next day is the variant (popular practice)", None),
    },
    "pongal": {
        "tamil_rule_day_ingress": ("Pongal, Thai 1: the Sun enters sidereal Makara between sunrise and sunset, so the solar month Thai begins that day (the Tamil Rule); computed at Chennai for every city", "The Indian Calendar (Sewell and Dīkshit, 1896), Art. 28, p. 12"),
        "tamil_rule_night_ingress": ("Pongal, Thai 1: the Sun enters sidereal Makara after sunset or before dawn, so Thai begins at the next sunrise (the Tamil Rule); computed at Chennai for every city", "The Indian Calendar (Sewell and Dīkshit, 1896), Art. 28, p. 12"),
    },
    "lohri": {
        "eve_of_ingress_day": ("Lohri is kept on the evening before the day, counted from sunrise to sunrise at Amritsar, in which the Sun enters sidereal Makara; that day is Maghi. One date for every city, with no time (popular practice; no text read gives the day)", None),
    },
    "vishu": {
        "first_sunrise_after_ingress": ("Vishu is kept on the day whose sunrise is the first after the Sun enters sidereal Mesha, computed at Kochi for every city; the Kani is the first sight of that morning (our reading of the kept days and of the Malabar and Travancore manuals; popular practice)", None),
    },
    "tamil-new-year": {
        "tamil_rule_day_ingress": ("Tamil New Year, Chittirai 1, is the day itself when the Sun enters sidereal Mesha between sunrise and sunset at Chennai, by the Tamil Rule; one date for every city", "The Indian Calendar (Sewell and Dīkshit, 1896), Art. 28, p. 12"),
        "tamil_rule_night_ingress": ("Tamil New Year, Chittirai 1, begins at the next sunrise when the Sun enters sidereal Mesha after sunset or before dawn at Chennai, by the Tamil Rule; one date for every city", "The Indian Calendar (Sewell and Dīkshit, 1896), Art. 28, p. 12"),
    },
    "baisakhi": {
        "day_holding_ingress": ("Baisakhi is kept on the day, counted from sunrise to sunrise at Amritsar, in which the Sun enters sidereal Mesha, as for Lohri's Maghi; one date for every city, with no time (popular practice; no text read gives the day)", None),
    },
    "gangaur": {
        "sunrise_tritiya": ("Gangaur, the Gauri-tritiya, is kept on the day whose sunrise the Caitra shukla Tritiya holds, even by a trace; a Tritiya joined to any Dvitiya is barred", "Dharmasindhu p. 9"),
        "two_sunrises_later": ("When the Tritiya holds two sunrises, the later, Caturthi-joined day is taken", "Dharmasindhu p. 9"),
        "kshaya_dvitiya_joined": ("When the Tritiya holds no sunrise, the Dvitiya-joined day on which it begins is taken", "Dharmasindhu p. 9"),
    },
    "vinayaka-chaturthi": {
        "next_day_midday": ("Vinayaka Chaturthi is kept on the later day when the shukla Caturthi reaches that day's midday, the rule the site keeps for Ganesha Chaturthi (the monthly keeping is popular practice)", "Nirṇaya-sindhu p. 47 (Bṛhaspati)"),
        "trtiya_joined_earlier": ("When the Caturthi does not reach the later day's midday, it is kept on the earlier day, joined with the Trtiya", "Nirṇaya-sindhu p. 47 (Bṛhaspati)"),
    },
    "skanda-sashti": {
        "panchami_joined_by_day": ("Skanda Shashthi is kept on the day on which the shukla Shashthi begins between sunrise and sunset, joined to the Panchami; the joining by day is our reading", "Vratarāja f. 108; Nirṇaya-sindhu p. 48; Dharmasindhu pp. 9–10"),
        "first_sunrise_in_shashthi": ("When the Shashthi begins at night, it is kept on the first day whose sunrise the Shashthi holds (our reading of the joining by day)", "Vratarāja f. 108; Nirṇaya-sindhu p. 48; Dharmasindhu pp. 9–10"),
        "night_only_day_it_begins": ("When the Shashthi lies wholly within one night, which happens only far north, it is kept on the day on whose night it falls (our reading)", None),
    },
    "kalashtami-monthly": {
        "midday": ("The monthly Kalashtami is kept on the day whose midday the krishna Ashtami covers, when only one day's midday has it", "Dharmasindhu p. 10"),
        "midday_both_earlier": ("When the Ashtami covers midday on both days, wholly or in part, the earlier day is kept", "Dharmasindhu p. 10"),
        "midday_neither_sunrise_day": ("When the Ashtami covers neither midday, the day whose sunrise it holds is kept (our reading)", None),
        "pradosha_only_earlier_ds": ("When the earlier day has the Ashtami only at pradosha and the later only at midday, the pradosha day is kept, as Dharmasindhu judges from the conduct of many learned people", "Dharmasindhu p. 10"),
    },
    "rang-panchami": {
        "sunrise": ("Rang Panchami is kept on the day whose sunrise the dark Panchami after Holi holds (popular practice; no text read gives the day)", None),
        "two_sunrises_first": ("When the Panchami holds two sunrises, the first of those days is kept (popular practice)", None),
        "no_sunrise_day_it_falls_on": ("When the Panchami holds no sunrise, the day in which it begins is kept (popular practice)", None),
    },
    "cheti-chand": {
        "sunset": ("Cheti Chand is kept on the day whose sunset the Caitra shukla Dvitiya holds, computed at Ahmedabad for every city (popular practice; no text read gives the day)", None),
        "two_sunsets_first": ("When the Dvitiya holds two sunsets, the first of those days is kept (popular practice)", None),
        "no_sunset_sunrise_day": ("When the Dvitiya holds no sunset, the day whose sunrise it holds is kept (popular practice)", None),
    },
    "sheetala-ashtami": {
        "sunrise": ("Sheetala Ashtami (Basoda) is kept on the day whose sunrise the dark Ashtami after Holi holds (popular practice; no text read gives the day)", None),
        "two_sunrises_first": ("When the Ashtami holds two sunrises, the first of those days is kept (popular practice)", None),
        "no_sunrise_day_it_falls_on": ("When the Ashtami holds no sunrise, the day in which it begins is kept (popular practice)", None),
    },
    # Decisions 44-45 (festivals.md s35-36, 18 Oct 2026): popular practice.
    "kali-puja": {
        "nishitha": ("Kali Puja is kept on the night whose nishitha, the middle muhurta of the night, falls in the Amavasya (popular practice; no text read gives the day).", None),
        "nishitha_both_more": ("When the Amavasya covers nishitha on both nights, the night with more of it is kept, and the earlier night if the two are equal (popular practice).", None),
        "nishitha_neither_later": ("When the Amavasya covers nishitha on neither night, the later night is kept, as it holds the Amavasya at pradosha (our reading).", None),
    },
    "ahoi-ashtami": {
        "pradosha": ("Ahoi Ashtami is kept on the day whose pradosha, the three muhurtas after sunset, falls in the dark Ashtami (popular practice; no text read gives the day).", None),
        "pradosha_both_more": ("When the Ashtami covers pradosha on both days, the day with more of it is kept, and the earlier day if the two are equal (popular practice).", None),
        "pradosha_neither_later": ("When the Ashtami covers pradosha on neither day, the later day is kept, as its sunrise holds the Ashtami (our reading).", None),
    },
    "vaikuntha-ekadashi": {
        "margazhi_leading_day": ("Vaikuntha Ekadashi: the shukla Ekadashi whose Smarta fast falls in Margazhi, the Tamil solar month, which begins on the day the Sun enters sidereal Dhanus if it enters before sunset, otherwise on the next day; chosen at Chennai for every city (popular practice; no text read gives the day)", "The Indian Calendar (Sewell and Dīkshit, 1896), Art. 28, p. 12"),
    },
    "durga-puja": {
        "sunrise_ashtami": ("Mahashtami: the Ashtami current at sunrise for a muhurta, joined to the Navami", "Tithi-tattva pp. 87–89"),
        "complete_first_day": ("The Ashtami holding two sunrises: the complete first day", "Tithi-tattva p. 88"),
        "kshaya_day_it_falls_on": ("A tithi holding no sunrise: the day it falls on (our reading of TT's two-day worship, p. 89)", "Tithi-tattva p. 89"),
        "sunrise_saptami": ("The leaf entry: the Saptami current at sunrise, in the forenoon, with or without Mula", "Tithi-tattva p. 76"),
        "kshaya_shashthi_joined": ("A lost Saptami: the Shashthi-joined day it falls on", "Tithi-tattva p. 89"),
        "sunrise_navami": ("Mahanavami: the day after the sandhi, on the Navami current at sunrise", "Tithi-tattva p. 88"),
        "sunrise_dashami": ("The immersion: the Dashami current at sunrise, in the forenoon, never at night", "Tithi-tattva pp. 86–87"),
        "short_dashami_day_before": ("A Dashami lasting under a muhurta after sunrise: the Aparajita puja and the immersion on the day before", "Tithi-tattva p. 89"),
        "evening_before_leaf_entry": ("Bodhana and amantrana together, the Shashthi holding the evening before the leaf entry", "Tithi-tattva p. 75"),
        "shashthi_evening": ("Bodhana in the Shashthi's evening twilight at a bilva tree, the amantrana the evening before the leaf entry", "Tithi-tattva pp. 73–75"),
        "neither_evening_forenoon": ("The Shashthi in neither evening: bodhana in the later day's forenoon Shashthi", "Tithi-tattva p. 75"),
    },
    "durgashtami": {
        "sunrise_navami_joined": ("The Ashtami current at sunrise, even for a ghatika, joined to the Navami; never one touched by the Saptami", "Dharmasindhu p. 69; Nirṇaya-sindhu pp. 262–263"),
        "under_one_ghatika_earlier": ("The Ashtami lasts under a ghatika after that sunrise: the earlier day", "Dharmasindhu p. 69; Nirṇaya-sindhu p. 264"),
        "navami_no_sunrise_earlier": ("The Navami touches no sunrise: the earlier day", "Dharmasindhu p. 69; Nirṇaya-sindhu p. 264 (Smṛti-saṃgraha)"),
        "full_first_day": ("The Ashtami fills the whole first day and only about a muhurta of the next: the complete first day", "Dharmasindhu p. 69"),
        "ashtami_no_sunrise_earlier": ("The Ashtami touches no sunrise: the day it falls on", "Dharmasindhu p. 69"),
    },
    "mahanavami": {
        "navami_three_muhurtas_evening": ("The Navami, joined to the Ashtami, covers three muhurtas of that day's evening before sunset: that day", "Nirṇaya-sindhu pp. 272–273; Dharmasindhu p. 69"),
        "navami_later": ("Under three muhurtas before sunset: the later day", "Nirṇaya-sindhu p. 273; Dharmasindhu p. 69"),
    },
    "ramanavami": {
        "midday_earlier_only": ("The Navami covers midday on the earlier day only: that day", "Nirṇaya-sindhu p. 119; Dharmasindhu p. 33"),
        "later_day": ("Midday on both days, or on neither: the later day, even if the earlier has Punarvasu", "Nirṇaya-sindhu p. 119; Dharmasindhu p. 33"),
        "short_later_earlier": ("The later day's Navami lasts under three muhurtas after sunrise, or touches no sunrise: everyone keeps the Ashtami-joined day", "Dharmasindhu p. 33"),
        "smarta_vaishnava_split": ("The later day holds, but the Dashami touches no sunrise, so the parana day is the Smartas' Ekadashi: Smartas keep the earlier day (smartaDate), Vaishnavas the later (vaishnavaDate)", "Nirṇaya-sindhu pp. 119–120; Dharmasindhu p. 33"),
    },
    "vasantotsava": {
        "vasantotsava_sunrise": ("The spring festival: the dark Pratipada current at sunrise after the Holika Purnima; at sunrise on both days, the earlier", "Nirṇaya-sindhu p. 345; Dharmasindhu p. 95"),
        "vasantotsava_no_sunrise": ("The Pratipada touches no sunrise: the day it falls on (our reading, as Dharmasindhu p. 31 rules for the new year under the same verse)", "Nirṇaya-sindhu p. 345; Dharmasindhu pp. 31, 95"),
    },
    "vijayadashami": {
        "aparahna": ("The Dashami in the afternoon of one day only: that day", "Nirṇaya-sindhu p. 284"),
        "aparahna_both_earlier": ("In the afternoon of both days, covering or touching it: the earlier", "Nirṇaya-sindhu p. 284"),
        "shravana_later": ("In the afternoon of both days, with Shravana in the later day's afternoon: the later", "Nirṇaya-sindhu pp. 283–284; Dharmasindhu p. 71"),
        "pradosha_both_later": ("Pradosha on both days, the afternoon only on the later: the later", "Nirṇaya-sindhu p. 284"),
        "pradosha": ("No afternoon on either day: the day with pradosha, the secondary time", "Nirṇaya-sindhu p. 284"),
        "neither_later": ("Neither window on either day: the later day (our fallback)", None),
    },
    "holika-dahana": {
        "pradosha_later": ("Pradosha on both days, or partly on the second: the second, since Bhadra falls on the first", "Dharmasindhu p. 94; Nirṇaya-sindhu p. 342"),
        "pradosha": ("The Purnima at the first day's pradosha, free of Bhadra (Nārada)", "Dharmasindhu p. 94; Nirṇaya-sindhu p. 342"),
        "sardha_triyama_later": ("The first pradosha in Bhadra; the Purnima lasts 3 1/2 yamas into the second day and the Pratipada grows: the second day's pradosha, in Pratipada (Bhaviṣya)", "Dharmasindhu p. 94; Nirṇaya-sindhu p. 343"),
        "shrinking_pratipada_tail": ("As above but the Pratipada shrinks: the first night, in Bhadra's tail or in Bhadra avoiding its face", "Dharmasindhu p. 94"),
        "after_bhadra_before_midnight": ("The first pradosha in Bhadra, which ends before midnight: once it ends, before midnight (the midnight limit is our reading)", "Dharmasindhu p. 94"),
        "bhadra_avoiding_face": ("Bhadra ends after midnight: at pradosha in Bhadra, avoiding only its face (the others in Nirṇaya-sindhu; 'the practice of the learned')", "Dharmasindhu p. 94; Nirṇaya-sindhu pp. 343–344"),
        "neither_tail": ("Pradosha on neither day: the first night, in Bhadra's tail", "Dharmasindhu p. 94"),
        "neither_after_pradosha": ("Pradosha on neither day and no tail at night: in Bhadra after pradosha, avoiding its face (a first-half Bhadra is allowed at night, MC 1.44)", "Dharmasindhu p. 94"),
    },
    "magha-snana": {
        "pausha_later_day": ("The Pausha Purnima on the panchang's vrata day: the later day, whose sunrise the Purnima holds (our reading; no text read rules on it separately)", None),
        "amavasya_pratipad_pair": ("The Amavasya joined to the Pratipada: the later day, whose sunrise the Amavasya holds", "Dharmasindhu p. 6"),
        "maghi_later_day": ("The Maghi Purnima is the later day, whose sunrise the Purnima holds", "Nirṇaya-sindhu p. 333"),
        "only_day": ("The tithi holds no sunrise: the day it falls on", None),
        "first_sunrise": ("The first sunrise in the tithi: the month's start is a span marker (our reading)", None),
        "last_sunrise": ("The last sunrise in the tithi: the month's end is a span marker (our reading)", None),
        "month_regular": ("No adhika or lost month falls in the season", None),
        "month_adhika_pausha": ("An adhika month allows no start, so the bathing begins in the nija Pausha (our reading)", "Dharmasindhu p. 4"),
        "month_adhika_magha": ("When Magha is adhika, the bath and its rules run through both Maghas and close in the nija Magha", "Dharmasindhu p. 87"),
        "month_kshaya": ("When a month is lost, the bathing begins on the Purnima of the lost month holding the Makara sankranti and closes on the Magha Purnima joined to the Kumbha sankranti", "Dharmasindhu p. 4"),
        "month_kshaya_solar": ("When one lost month holds both the Makara and the Kumbha sankranti, the texts read give no bounds for the bathing month; Dharmasindhu's solar reckoning is used", "Dharmasindhu p. 86"),
        "trayodashi": ("Most: the three days from the Trayodashi, Magha shukla Trayodashi, Caturdashi and Purnima, counted as three days ending on the Maghi Purnima day (the count is our reading)", "Nirṇaya-sindhu p. 323; Dharmasindhu p. 87"),
        "makara_ratha_maghi": ("Some: Makara sankranti, Ratha-saptami and the Maghi Purnima", "Nirṇaya-sindhu p. 323"),
        "from_dashami": ("Others: three days from Magha shukla Dashami, from the first sunrise in it (the dating is our reading)", "Nirṇaya-sindhu p. 323"),
        "makara_first_three": ("Others: the first three days of the Sun in Capricorn, from the Makara bath day (the dating is our reading)", "Nirṇaya-sindhu p. 323"),
        "magha_first_three": ("Some: the first three days of Magha, from the first sunrise in the month (the dating is our reading)", "Nirṇaya-sindhu p. 323"),
    },
}  # fmt: skip
# Magh Mela (contract 7t; research's magha-snana.md v3, adopted by the lead 17 Oct 2026).
MAGHA_MARKS = {
    "month_start": ("The start of the month's bathing, Pausha shukla Ekadashi or the Purnima", "Nirṇaya-sindhu p. 319; Dharmasindhu p. 86"),
    "solar_start": ("The solar start of the month: the bath from the Sun's entry into Capricorn to its entry into Aquarius", "Dharmasindhu p. 86"),
    "texts_day_popular_name": ("The texts' own day: the Amavasya between the Pausha and Magha full moons, inside the bathing month and the day of the ardhodaya yoga when it falls. Only the name Mauni Amavasya is popular; silence is the rule for every bath of the month (Nirṇaya-sindhu p. 321)", "Nirṇaya-sindhu p. 318; Dharmasindhu p. 87"),
    "inside_month_not_named": ("Inside the bathing month, where the daily bath applies, but no text read singles it out as a bathing day", "Nirṇaya-sindhu p. 319; Dharmasindhu p. 86"),
    "texts_day": ("At Prayaga at first light, 'equal to ten million solar eclipses'", "Nirṇaya-sindhu p. 330"),
    "month_end": ("The end of the month's bathing, Magha shukla Dvadashi or the Purnima", "Nirṇaya-sindhu p. 319; Dharmasindhu p. 86"),
    "lost_month_purnima": ("The lost month has one full moon. Dharmasindhu counts each tithi of a lost month in both of its months, so this is both the Pausha and the Magha Purnima (our reading). This season the bathing month is the Sun's Makara-to-Kumbha span, and the full moon falls inside it", "Dharmasindhu pp. 3, 86; Nirṇaya-sindhu p. 21"),
    "lost_month_amavasya": ("The lost month has one Amavasya. Dharmasindhu counts each tithi of a lost month in both of its months, so this is the Amavasya closing Pausha (our reading): the texts' own day, and the day of the ardhodaya yoga when it falls. This season no Amavasya falls between the Pausha and Magha full moons, which are one. It is inside the Sun's Makara-to-Kumbha bathing month. Only the name Mauni Amavasya is popular; silence is the rule for every bath of the month (Nirṇaya-sindhu p. 321)", "Dharmasindhu pp. 3, 87; Nirṇaya-sindhu pp. 21, 318"),
    "outside_month": ("Outside the Magha bathing month, which ends on Magha shukla Dvadashi or the Purnima. It lies in the dark half of the amanta month of Magha, so outside means outside the bathing month, not the calendar month. No text read names it a Prayaga bath", "Nirṇaya-sindhu p. 319; Dharmasindhu p. 86"),
}  # fmt: skip
MAGHA_NOTES = {
    "basis": "By the texts, Magha-snana is a month of dawn bathing, most praised at Prayaga's confluence. It runs from Pausha shukla Ekadashi or Purnima to Magha shukla Dvadashi or Purnima, or by the Sun from Makara to Kumbha (Nirṇaya-sindhu pp. 319–322; Dharmasindhu pp. 86–87)",
    "start_options": "Dharmasindhu also lets the bathing begin on the Pausha Purnima or the Amavasya (p. 86)",
    "hour": "From first light to morning: best while the stars show, middling when they have faded, lesser after sunrise (Nirṇaya-sindhu p. 322; Dharmasindhu p. 86)",
    "silence": "In silence, with the daily arghya to the Sun (Nirṇaya-sindhu p. 321)",
    "who": "Everyone may bathe: the student, the householder, the forest-dweller and the renunciant; children, the old and the young; men, women and those of the third sex (Nirṇaya-sindhu p. 320, the Bhaviṣya; Dharmasindhu pp. 86–87)",
    "standing": "It is both obligatory and elective (Dharmasindhu p. 87; Nirṇaya-sindhu p. 323)",
    "rules": "The month's rules: no fire for warmth after the bath, only for homa; sesame with sugar given daily; no oil massage and no radish; sleeping on the ground, havishya food and continence; gifts of fuel, blankets, clothes, sandals, oil, ghee, quilts, gold and food (Nirṇaya-sindhu p. 323, the Nāradīya; Dharmasindhu p. 87)",
    "sesame": "Bathing with sesame, rubbing with sesame, offering sesame in the fire and in water, eating sesame and giving sesame: the six uses of sesame (Nirṇaya-sindhu p. 324)",
    "close": "The close: 'Divakara, lord of the world, Prabhakara, salutation to you; make this Magha bath complete, lord of the dawn' (Nirṇaya-sindhu p. 325)",
    "prayaga": "The bath is most praised at Prayaga: at the confluence of the Ganga and the Yamuna it is a hundred times that at Kashi (Nirṇaya-sindhu p. 322). Dharmasindhu grades the water: home-heated water gives six years' fruit, the Ganga a thousandfold, and the confluence a hundred times that (p. 87)",
    "anywhere": "Bathing anywhere, with Prayaga in mind (Dharmasindhu p. 87; Nirṇaya-sindhu p. 322, the Brahma)",
    "kashi": "If Prayaga is out of reach, the Prayaga tirtha at Kashi, north of Dashashvamedha (Nirṇaya-sindhu p. 324, the Kāśī-khaṇḍa)",
    "three_days_prayaga": "Three days' bathing at Prayaga in Magha gives a fruit that a thousand horse sacrifices do not (Nirṇaya-sindhu p. 323, the Padma)",
    "veni_dana": "At Prayaga, the veni-dana, the offering of the hair, with shaving for all (Dharmasindhu p. 88)",
    "fewer_days": "If the whole month is not possible, three days or one (Nirṇaya-sindhu p. 323)",
    "ardhodaya": "Ardhodaya: the Amavasya between the Pausha and Magha full moons falling with a Sunday, the Vyatipata yoga and Shravana, 'equal to ten million solar eclipses' (Dharmasindhu p. 87; Nirṇaya-sindhu p. 318, the Skanda via Hemādri). The four must meet at one instant within the Sunday, sunrise to sunrise at Prayagraj (our reading)",
    "ardhodaya_night": "NS counts a night ardhodaya; DS does not",
    "mahamaghi": "Mahamaghi: Jupiter and the Moon in Magha on the Magha full moon (Nirṇaya-sindhu p. 333, the Brahma via Hemādri); both in sidereal Magha at one instant within the Purnima (our reading)",
    "shivaratri_solar": "Mahashivaratri is inside the Makara-to-Kumbha span only if the sunrise of its vrata day, the morning of the bath, comes before that year's Kumbha sankranti",
}  # fmt: skip
FESTIVAL_NOTES = {
    "dipavali": "Lakshmi is worshipped at pradosha on this day (Bhaviṣya, NS p. 299). Divodāsīya prefers an Amavasya covering both pradosha and midnight (NS p. 300); nishithaCovered says whether it does. No fixed-lagna (Vrishabha) muhurat is sourced.",
    "dhanteras": "The dark Trayodashi two days before the Dipavali Amavasya. The texts give one rite for it: a lamp for Yama set outside the house at nightfall, so that untimely death is averted (Skanda via the Nirṇayāmṛta, NS p. 294; DS p. 76). yamaDipa is that day's pradosha while the Trayodashi runs, or the whole pradosha when it runs at neither. Nirṇaya-sindhu's print reads 'the bright fortnight'; its own Hindi, its order and DS put it in the dark one. The names Dhanteras and Dhanvantari, and buying metal, are not in NS or DS. Nārada has lamps waved in the early night for five tithis from the dark Dvadashi (NS p. 294, DS p. 76).",
    "narakaChaturdashi": "An oil bath with sesame oil before sunrise, at moonrise (Bhaviṣyottara via Hemādri, NS p. 294; DS p. 76). Of the night's last yama, arunodaya (four ghatikas before sunrise, NS p. 297) and moonrise to sunrise, each later time is better; abhyangaSnana is the main time, from moonrise or the Caturdashi's start to sunrise. If none can be kept, the bath is still taken after sunrise (DS p. 77). Apamarga is waved during the bath and Yama-tarpana follows (NS pp. 297–298, DS p. 77); lamps are given at pradosha (lamps), at that day's sunset even when the bath fell on the second day (DS p. 76). The Divodāsīya gives the lamps on the first evening and the bath the next morning (NS p. 297).",
    "govardhan": "The Kartika shukla Pratipada: the oil bath, Bali's worship, the cow play and Govardhana-puja, the margapali, new clothes and the women's nirajana (DS p. 78). Govardhana is worshipped in the morning (Skanda via Hemādri, NS p. 303): govardhanPuja is the morning, the 1st fifth of the daytime (our reading of NS p. 28), while the Pratipada runs. Bali is worshipped at night (Bhaviṣya, NS p. 301): baliPuja is that night. Away from the hill, Govardhana is made of cow-dung or as a heap of food, the annakuta (DS p. 78). variantDate is Nirṇaya-sindhu's day (pp. 301–302): the later day only when the Pratipada reaches that day's sayahna, the 5th fifth of the daytime.",
    "bhaiDooj": "Yama-dvitiya: Yamuna fed Yama, her brother, at her home on this day (DS p. 79; NS p. 305). A man eats from his sister's hand, not at home, and honours his sisters with clothes and ornaments. yamaPuja is the afternoon, the 4th fifth of the daytime, when Yama is worshipped with Citragupta and his messengers (DS p. 79; Skanda via Hemādri, NS p. 304). NS reports two other views without choosing: the Nirṇayāmṛta takes the Dvitiya joined with the Pratipada, Hemādri the one covering midday.",
    "mahashivaratri": "The dark Chaturdashi ending amanta Magha (purnimanta Phalguna). Some texts take pradosha, others midnight (NS p. 334). A Chaturdashi joined with Amavasya is avoided (Skanda, p. 337).",
    "masik-shivaratri": "Every dark Chaturdashi, by the same tests (NS p. 340). Hemādri keeps the name for the Magha one only and takes the day with more of the night, the earlier when equal.",
    "ganesha-chaturthi": "Worship at midday (pujaWindow, the 3rd fifth of the daytime, NS p. 28). Do not look at the Moon while the Chaturthi runs (moonAvoid; Mārkaṇḍeya in NS p. 198); a Moon that rose in Chaturthi may be seen once Panchami begins.",
    "raksha-bandhan": "The Shravana Purnima. Dharmasindhu p. 49 sets the day by how long the Purnima lasts after the later sunrise; tieWindow is that day's afternoon (the 4th fifth of the daytime, our reading) or pradosha, free of Bhadra. Nirṇaya-sindhu p. 180 keeps the earlier day's afternoon, after Bhadra even at night, and never the Purnima joined with Pratipada; its day is variantDate where it differs. bhadra is the Vishti karana, the Purnima's first half. It is kept on eclipse and sankranti days too.",
    "janmashtami": "The dark Ashtami ending amanta Shravana (purnimanta Bhadrapada). Midnight decides (NS p. 189). Jayanti is the Ashtami joined with Rohini; NS holds both vratas due, though people keep only Janmashtami (p. 187). In a split year the date is the Rohini day (Mādhava, Dharmasindhu pp. 50–51) and variantDate is Nirṇaya-sindhu's first-day fast (it keeps both, p. 192). udayaDate is the sunrise view, which Vaishnava calendars follow; NS sets it aside as baseless (p. 191).",
    "sharad-navaratri": "Kalasha-sthapana on Ashvina shukla Pratipada. sthapanaWindow is the first ten ghatikas (four hours) after sunrise while the Pratipada runs, failing that the Abhijit muhurta; never in the afternoon or at night (Dharmasindhu pp. 65–66). muhurtasAfterSunrise is how long the Pratipada lasts after that sunrise. cautions lists the Pratipada's first sixteen nadis, Chitra and Vaidhriti where they touch the window: avoided where the time allows, never at the cost of the forenoon (DS p. 65).",
    "karva-chauth": "Karaka-caturthi, kept by women for their marital good fortune, sons and lasting prosperity (Vratarāja f. 81). In the evening, at nightfall (f. 82), Gauri, Shiva, Ganapati and Shanmukha are worshipped under a drawn banyan, ten pots (karaka) with food are given to brahmanas and pots are exchanged with married women; the arghya is given to the Moon after moonrise (f. 81). The fast lasts until that arghya: our reading of the katha (ff. 81–82), in which eating at a false moonrise is the fault. sunset is that day's sunset and moonrise its moonrise (upper limb, as for Sankashti). The pre-dawn meal (sargi), the sieve and a fixed puja muhurat are not in the texts read.",
    "tulsi-vivah": "Dharmasindhu pp. 81–82 allows the Tulasi marriage on any of the three days from the Navami, any day from the Ekadashi to the Purnima, or under a marriage nakshatra in the Kartika bright fortnight, but records that it is done everywhere with the Prabodhotsava, the waking of Vishnu, in the early night of the parana day; window is that early night (pradosha, our reading). Nirṇaya-sindhu p. 306 (the Padma via Hemādri) has a golden Hari worshipped with Tulasi for three days from the Navami, then the marriage rite. variantDate is the Vaishnava parana day where it differs. The rite: Vishnu as Damodara and Tulasi are bathed with turmeric, the god woken with bells, a curtain held between them during the mangalashtaka verses, and Tulasi given to Damodara as a bride (DS p. 82).",
    "tripurotsava": "Popularly Dev Deepawali, a name in none of the texts read. On the Kartika Purnima at dusk the Tripurotsava is held and lamps are given in temples, so that the creatures that see them are not born again (Bhārgavārcana-dīpikā in NS p. 312; DS p. 84). window is that day's pradosha while the Purnima runs. The Purnima is especially holy with Krttika (maha-kartiki with Rohini), and the bull-release and great gifts belong to it (DS p. 84).",
    "vasanta-panchami": "The spring festival begins on the Magha shukla Panchami, and Rati and Kama are worshipped (Dharmasindhu p. 89). The Vratarāja (f. 103, from Hemādri) has an oil bath, ornaments, and Hari worshipped with gulal, scents and food, then brahmanas fed; its own day rule takes the Panchami covering midday, the earlier day when it covers both or neither. Nirṇaya-sindhu p. 329 names the day Shri-panchami, with Shri worshipped with kunda flowers; Mādhava takes the earlier day, Hemādri the later. forenoon is sunrise to midday, our reading of DS's forenoon. Sarasvati is worshipped in the forenoon of the Caturthi-joined Panchami (the Saṃvatsara-pradīpa in Raghunandana's Tithi-tattva, p. 34), which is DS's earlier day; NS, DS and the Vratarāja do not name her for this day.",
    "ratha-saptami": "The bath at arunodaya (the 96 minutes before sunrise) on this Saptami equals one at a solar eclipse (Vishnu in the Candrikā, NS p. 330). It is taken in still water with a lamp on the head, seven arka and seven badari leaves, and the mantra 'hara makari saptami'; then the arghya to the Sun, and gifts of a golden Sun or sesame cakes (NS pp. 330–332; DS p. 89). A single meal on the Shashthi. It is also a Manvadi, whose shraddha takes the forenoon (NS p. 332).",
    "bhishma-ashtami": "Tarpana with sesame water to Bhishma is obligatory and open to every varna; a shraddha for offspring is optional (NS pp. 332–333; DS pp. 89–90). It is done with the thread reversed, then the arghya. Nirṇaya-sindhu lets a man whose father is living do it (the Padma); Dharmasindhu notes the Kaustubha says no and most say yes. tarpanaWindow is midday, the 8th and 9th day-muhurtas, as for every ekoddishta (NS p. 718).",
    "kalashtami": "Kalashtami, the dark Ashtami ending amanta Kartika (Margashirsha krishna purnimanta), popularly Kaal Bhairav Jayanti; the name Jayanti is not in the texts, though NS p. 313 tells Bhairava's birth from the Shiva-rahasya. A fast, arghya, a night vigil and worship in the four night watches; three arghyas after worshipping Kalabhairava (NS pp. 312–313; DS p. 84). Nirṇaya-sindhu takes the Ashtami covering midday, since Bhairava was born at midday, and rejects the pradosha view. vigil is the day of the night vigil, which NS takes on its own: the Ashtami touching the night (sunset to sunrise), and the later day when it touches both nights in part (NS pp. 312–313); one night wholly covered and the other only touched gives the whole one (our reading). Dharmasindhu (p. 84) keeps that rule but decides by pradosha when the earlier day has the Ashtami only at pradosha and the later only at midday, following the conduct of many learned people; that pradosha day is the date then, its puja window the pradosha, and variantDate is Nirṇaya-sindhu's midday day. When the Ashtami covers neither midday, variantDate is the Kaustubha's pradosha rule (both days: the later), which DS also reports.",
    "dattatreya-jayanti": "Dattatreya's birth on the Margashirsha Purnima (the Skanda, Sahyādri-khaṇḍa, NS p. 315; DS p. 84), taken covering pradosha. pujaWindow is that pradosha while the Purnima runs.",
    "ganesha-jayanti": "In the texts this is the Varada, Tila or Vinayaka Caturthi of Magha shukla; Ganesh Jayanti, Ganesha's birth, is the popular name and is not stated in them. The Vinayaka-vrata follows the Bhadrapada midday rule (DS p. 89); the night-meal vow to Dhundhiraja with sesame laddus (the Tila or Varada Caturthi) takes the Caturthi covering pradosha (DS p. 89; NS p. 329; Vratarāja f. 82). pujaWindow is the chosen day's midday.",
    "holashtak": "Muhūrta-cintāmaṇi 1.40 avoids the eight days before Holika, the Phalguna shukla Ashtami to the Purnima (the Śīghrabodha in the commentary), for marriage and other auspicious acts only on the banks of the Beas, Ravi and Sutlej and at Pushkar; the same work says that elsewhere the days are auspicious. The muhurta finder does not apply it.",
    "akshaya-tritiya": "The Vaishakha shukla Tritiya, one of the four yugadis, the days a yuga began; the texts differ on which yuga (DS p. 36; NS p. 135). Nothing offered or given on it perishes (the Bhaviṣya, Vratarāja f. 44; DS p. 36): a Ganga bath, a barley homa, Krishna worshipped with sandal, japa, homa, ancestral tarpana and a yugadi shraddha in the forenoon, a water pot given to the gods and ancestors, and the season's gifts: barley, wheat, chickpeas, sattu, umbrellas, sandals, cows, land, gold and clothes (VR f. 44). Buying gold, or buying anything, is not in the texts read; gold appears only as a gift. Especially holy with Rohini or on a Wednesday (DS), or with Krttika (VR). The date follows Dharmasindhu p. 36 when the Tritiya covers both forenoons; variantDate is Nirṇaya-sindhu's later day.",
    "parashurama-jayanti": "On the same Tritiya, Parashurama's birth in the first watch of the night (the Bhaviṣya, VR f. 43): he is worshipped at pradosha and given arghya (DS p. 37). firstWatch is the night's first quarter; arghyaWindow is pradosha.",
    "guru-purnima": "In the texts this is the Vyasa-puja of ascetics on the Ashadha Purnima: saṃnyasins shave and worship Krishna, Vyāsa and his pupils, Śaṅkara and his, and the line of teachers, as they resolve to stay in one place for the four rainy months (DS pp. 43–44; NS p. 160). The name Guru Purnima, and a householder's worship of his own guru, are not in the pages read. pujaWindow is the morning. Where the Purnima holds the later sunrise for less than three muhurtas, Guru Purnima is also commonly kept on that sunrise day: it is variantDate, with variantBasis popular_practice (caution popular_sunrise_day). Also on this Purnima: the Kokila-vrata at dusk and Shiva's sleeping festival at pradosha (NS p. 160).",
    "durga-puja": "The Bengal Durga-puja by Raghunandana's Tithi-tattva (pp. 73–92). The span runs from the dark Navami of Ashvina to the bright Dashami; the Sun in Kanya adds merit and is not a condition (p. 73). Every act, from the leaf entry to the immersion, is on the tithi current at sunrise, even for a ghatika, which TT reads as a muhurta (pp. 87–89); with a tithi lost or gained the worship takes two or four days. Bodhana, the goddess's awakening, may also be on the dark Navami forenoon, ideally with Ardra (pp. 73–75). The evening twilight is three ghatikas after sunset, our reading. The leaf entry and the immersion are in a movable lagna or navamsa (p. 89), never at night; movableWindows lists those stretches of the forenoon. The sandhi is the last danda of the Ashtami and the first of the Navami, its bali given on the Navami (p. 86); the fast is on the puja day, not the sandhi day (p. 88). Mahanavami is on the sunrise Navami; nsDsDate gives Nirṇaya-sindhu's and Dharmasindhu's Mahanavami where it differs. Shravana is wanted for the immersion but does not move it (pp. 86–87).",
    "vat-savitri": "The Savitri vow: a woman fasts three nights from the Trayodashi and worships Savitri with Satyavat, an image of gold or clay on a prastha of sand in a bamboo vessel, with fruit, lamps, turmeric, a saubhagya thread, kunkuma and saffron; the story is read, a night vigil kept, and at dawn the image is given to a brahmana (the Bhaviṣya, NS p. 148). Unlike other Purnima and Amavasya fasts it is kept on the Caturdashi-joined day, even with 18 nadis of Caturdashi after sunrise (NS pp. 147–148), provided the tithi runs more than three muhurtas before that day's sunset (DS p. 41). nights are the vow's three nights; paranaAfter is the tithi's end, after which the fast is broken (NS p. 148). Southerners keep the Purnima form, westerners the Amavasya form, worshipping at the root of the banyan (NS p. 147). The texts do not say which new moon; the one before the Jyeshtha Purnima, ending amanta Vaishakha (purnimanta Jyeshtha's dark fortnight), is our reading. Neither form in an adhika month: no vow is begun or completed in it (DS p. 4). date is Dharmasindhu's day for the puja, which women everywhere keep without the fast (p. 41): the later day when the Caturdashi lasts 18 nadis (7 h 12 min) or more after the Caturdashi-joined day's sunrise, with the three-night fast on that earlier day (fastDate); the Amavasya form follows it through NS p. 148 (our reading). Shani Jayanti, kept on the same new moon today, is not in the texts read.",
    "ganga-dussehra": "Ganga-dashahara: the Jyeshtha shukla Dashami takes away ten sins (the Brahma via Hemādri, NS p. 143). Ten yogas make it: Jyeshtha, the bright fortnight, the Dashami, Wednesday, Hasta, Vyatipata, Gara karana, Ananda (Wednesday with Hasta, DS p. 38), the Moon in Kanya and the Sun in Vrishabha (the Skanda, NS p. 144; DS p. 38). yogas lists those meeting the Dashami in the chosen forenoon; the Varāha's Tuesday in place of Wednesday is settled by the difference of kalpas (NS p. 144). Rites: a bath and a sesame-water arghya at a river; a Ganga image of gold or silver, or of clay, or drawn in flour; ten each of flowers, lamps, food offerings and fruits; ten handfuls of black sesame with ghee and ten balls each of sattu and guda put in the water; the mantra 'om namah shivayai narayanyai dashaharayai namo namah' 5,000 times and the Gaṅgā-stotra ten times (NS pp. 144–145; DS pp. 38–39). In an adhika Jyeshtha it is kept in the adhika month, not the pure one (NS p. 144; DS p. 38). pujaWindow is the chosen forenoon while the Dashami runs.",
    "rath-yatra": "The chariot festival: on the Ashadha shukla Dvitiya joined with Pushya, Rama (Balarama) and Bhadra (Subhadra) are set on the chariot, the procession is held and many brahmanas are fed; without the star it is held on the tithi (the Skanda in the Tithi-tattva, quoted by NS p. 149). pushya is that star's span within the Dvitiya, when they meet. The texts give no rule for a Dvitiya spanning two days; the sunrise Dvitiya, Trtiya-joined, is our reading.",
    "sawan-somvar": "The Monday vow of Shravana: a fast for those able, otherwise one meal at night (DS p. 44); the Vratarāja has Monday vows (ff. 347–354): a fourteen-year vow with pradosha worship, a single-meal vow (f. 353) and an eight-Monday fast (f. 354). The texts do not say which month system. systems lists the month systems whose Shravana a Monday's sunrise falls in: purnimanta (North India, from the day after the Ashadha Purnima) or amanta (from the day after the Ashadha Amavasya); the two share only the Mondays of the bright fortnight. shravana gives each month's first and last day. Dharmasindhu also has Gauri worshipped on the Tuesdays of Shravana (p. 44).",
    "hariyali-teej": "In the texts this is the Madhushravanika, the first of three women's Tritiyas kept Caturthi-joined (Divodāsa in NS p. 197). The Vratarāja knows it in Gujarat as the Madhusrava and gives no rite, as it was not kept in its author's region, then gives a Svarna-gauri vow on this Tritiya, received by custom (Vratarāja, Internet Archive leaf 102). The name Hariyali and its present customs are not in the texts read. The day is the last whose sunrise has the Tritiya, by the Hartalika rule; muhurtasAfterSunrise is how long it lasts after that sunrise.",
    "kajari-teej": "In the texts this is the Kajjali, the dark Tritiya of Bhadrapada, the second of the three women's Tritiyas kept Caturthi-joined (Divodāsa in NS p. 197). Nirṇaya-sindhu counts its months purnimanta, so this is the dark Tritiya after the Shravana Purnima, where Kajari Teej falls today (our reading). The day is the last whose sunrise has the Tritiya, by the Hartalika rule.",
    "hartalika-teej": "The Haritalika, Bhadrapada shukla Tritiya: worship of Bhavani and Shiva and a fast are obligatory for women (DS p. 55). It is kept on the later, Caturthi-joined day even with a muhurta of Tritiya or less (Mādhava, NS p. 197; DS p. 55): the Caturthi-joined Tritiya removes widowhood and increases sons and grandsons, and the woman who keeps the Dvitiya-joined one meets widowhood (Āpastamba via Mādhava, NS p. 197). The Vratarāja's rite (ff. 48–52): a morning bath with sesame and amalaka paste, a resolve for the worship of Uma-Maheshvara with Ganapati first, a pavilion of plantain stems and silk, a sand linga with Parvati worshipped with flowers, incense, food and fruit, a night vigil, and the story heard with the husband. The name: Parvati was carried off (harita) by her companions (ali) (Vratarāja).",
    "nag-panchami": "Serpents are drawn in cow dung on both sides of the door and worshipped with curd, durva, kusha, scents and flowers, and brahmanas are honoured; those who worship them on this day have no fear of snakes anywhere (Hemādri's Bhaviṣya, NS p. 164). The Panchami is taken Shashthi-joined (the Camatkāra-cintāmaṇi, NS p. 164), within Dharmasindhu's muhurta limits (p. 44). muhurtas gives the Panchami's length after the later sunrise and the Caturthi's after the earlier, in day-muhurtas.",
    "rishi-panchami": "Bhadrapada shukla Panchami: the rishis are worshipped and only vegetables from unploughed land are eaten (DS p. 55). pujaWindow is midday, the 3rd fifth of the daytime, while the Panchami runs.",
    "anant-chaturdashi": "The Ananta vow: a golden image and a cord of fourteen knots, the details referred to the Kaustubha (DS p. 58). The date follows Dharmasindhu's sunrise rule (p. 58). Nirṇaya-sindhu takes the Caturdashi covering midday on either day and calls Mādhava's sunrise rule mistaken (pp. 210–211); its day is variantDate where they differ, which happens when the Caturdashi begins before midday on the earlier day and ends before midday on the later, at least two muhurtas after sunrise. pujaWindow is the forenoon, Dharmasindhu's main time, else midday, while the Caturdashi runs; Nirṇaya-sindhu puts the worship at midday (p. 210).",
    "chhath": "Popular practice; no text read gives the day. Our rule: the evening arghya (sandhyaArghya, at the city's sunset) on the first day whose sunrise falls within the Kartika shukla Shashthi, else the day whose sunset falls in it; where moving the Shashthi's start or end by one ghatika (24 minutes) would change the day, variantDate is the day the rule then gives (caution ghatika_margin); the morning arghya (ushaArghya) at the next sunrise; Kharna the day before the evening arghya and nahay-khay the day before that. Sun worship on a Shashthi is in the texts, but not this day or these rites: Dharmasindhu p. 55 has a Surya-shashthi on the Bhadrapada shukla Shashthi, and the Kṛtyaratnākara (pp. 447–448, the Bhaviṣya) a year-long Sun vow on the dark Shashthi of each month; on the Kartika Shashthi itself it gives an arghya to Karttikeya (p. 415). The fast, standing in water and the offerings are practice.",
    "chaiti-chhath": "Popular practice; no text read gives the day. The spring Chhath, kept by fewer than the Kartika one, on the Caitra shukla Shashthi by the same rule: the evening arghya (sandhyaArghya, at the city's sunset) on the first day whose sunrise falls within the Shashthi, else the day whose sunset falls in it; where moving the Shashthi's start or end by one ghatika (24 minutes) would change the day, variantDate is the day the rule then gives (caution ghatika_margin); the morning arghya (ushaArghya) at the next sunrise; Kharna the day before the evening arghya and nahay-khay the day before that. Sun worship on a Shashthi is in the texts, but not this day or these rites: Dharmasindhu p. 55 has a Surya-shashthi on the Bhadrapada shukla Shashthi, and the Kṛtyaratnākara (pp. 447–448, the Bhaviṣya) a year-long Sun vow on the dark Shashthi of each month. The fast, standing in water and the offerings are practice.",
    "hanuman-jayanti": "Popular practice; no text read gives the day. The main northern date is the Caitra Purnima, shown on the site's Purnima-vrata day. Other regional dates, not computed here: the Kartika krishna Caturdashi (some northern and western traditions), the new moon of the solar month Margazhi in Tamil Nadu, Vaishakha krishna Dashami in Andhra Pradesh and Telangana, Margashirsha shukla Trayodashi (the Hanumad-vrata) in Karnataka, and the Mesha sankranti in Odisha. No one regional date is the correct one.",
    "radhashtami": "Popular practice; no text read gives the day. Our rule: the Bhadrapada shukla Ashtami covering midday (the 3rd fifth of daylight); if it covers both middays or neither, the later day, whose sunrise holds the Ashtami. pujaWindow is that midday, by practice. Dharmasindhu gives this Ashtami to the Durvashtami and a Jyeshtha-devi puja (p. 56).",
    "onam": "Popular practice; no text read gives the day. A civil day is in Chingam when the Sun is in sidereal Simha at its sunrise. Onam (Tiruvonam, the Shravana nakshatra) is the Chingam day whose sunrise falls in Shravana with at least 6 nadikas (2 h 24 min) of it left, else the day before; the six-nadika test is our statement of common Kerala usage. When Chingam holds two Tiruvonams both are shown (twoTiruvonam) and the rule does not choose between them. Each Onam carries atham, the festival's opening on Atham (Hasta): the last day before that Tiruvonam whose sunrise falls in Hasta with 6 nadikas of it left, else the day before; it can fall in late Karkataka, before Chingam (our reading; popular practice). Atham and Tiruvonam are star-days, so the festival runs nine to eleven civil days, not always ten; give both dates. The textual days sharing the Vamana story, the Shravana-dvadashi and Vamana-jayanti, are lunar days and do not give Onam's date.",
    "vishwakarma-puja": "Popular practice; no text read gives the worship. The day is the Kanya sankranti's punyakala as /observances/sankranti computes it; only that basis is textual (Dharmasindhu p. 2; Nirṇaya-sindhu p. 5). In the Bengal calendar it is the last day of Bhadra.",
    "karthigai-deepam": "Popular practice, documented by Warren (Kala Sankalita, 1825, p. 401): Cartica Deepum, 'the day on which the Moon is in the Nacshatra Critica during the month Cartica'. One date for every city, computed at Tiruvannamalai: the day in the solar month Karttikai (the Sun in sidereal Vrischika, the month begun by the Tamil Rule of Sewell and Dīkshit's The Indian Calendar, 1896) whose sunset falls in Krittika; that sunset test is our rule, drawn from the days observed. When Krittika holds neither sunset, the evening on which it begins is taken, and the next day is also kept. When it holds both, the day that also has it at sunrise is taken (our reading). Where moving either end of Krittika by one ghatika (24 minutes) would change the day, the other day is given too (our reading). Two Krittika days in one Karttikai are both shown (twoKrittika) and the rule does not choose between them. The texts' lamps of the Karttika Purnima, the Tripurotsava (Nirṇaya-sindhu p. 312; Dharmasindhu p. 84), fall on the same day only in some years (tripurotsava). No time is given for lighting the lamps.",
    "pongal": "Thai Pongal is the first day of the Tamil solar month Thai, the Sun in sidereal Makara, by the Tamil Rule of Sewell and Dīkshit's The Indian Calendar (1896, Art. 28, p. 12): an ingress between sunrise and sunset starts the month that day, a later one at the next sunrise. That is also the southern usage for the Makara day (Nirṇaya-sindhu p. 326; Dharmasindhu p. 85). One date for every city, computed at Chennai. Warren (Kala Sankalita, 1825, p. 402) describes the boiled rice offered to the Sun and scattered over the fields, and the cattle worshipped and decked on Mattu Pongal, the day after; Dharmasindhu p. 86 gives the Makara rites: the bath, sesame, and the Sun bathed with milk. When the Sun enters Makara by day but less than three hours before sunset, Pongal is also commonly kept the next day (variantDate; popular practice, our reading), as it was on 15 Jan 2026. Bhogi, the day before, and Kanum Pongal, two days after, are popular practice, as are the four days as a set, the pot boiling over, sugarcane, kolam, Bhogi's bonfire, Kanu, Jallikattu and Thiruvalluvar Day. No time is given for setting the pot.",
    "lohri": "Popular practice; no text read names Lohri. It is kept on the evening before the day, counted from sunrise to sunrise at Amritsar, in which the Sun enters sidereal Makara; that day is Maghi, the first of Magh. One date for every city, with no time. Linking Maghi to Baudhāyana's two holy days after a night ingress, kept in the north (Nirṇaya-sindhu p. 327), is our reading. The bonfire, the Dulla Bhatti songs, rewri and gajak are popular practice.",
    "vishu": "Popular practice. Vishu is the day whose sunrise is the first after the Sun enters sidereal Mesha, computed at Kochi, with one date for every city: the Kani is set out the night before so that it is the first sight of that morning (Logan, Malabar, 1887, pp. 160–161; Nagam Aiya, The Travancore State Manual, 1906, pp. 366–367). That day is our reading of the kept days and of the two manuals. The Malabar month's own rule (Sewell and Dīkshit, 1896, Art. 28, rule b) can give a day earlier after a morning ingress, so Vishu is not called the first of Medam as a rule. No time is given for the Kani.",
    "tamil-new-year": "Tamil New Year (Puthandu) is Chittirai 1, the first day of the solar month with the Sun in sidereal Mesha, by the Tamil Rule of Sewell and Dīkshit's The Indian Calendar (1896, Art. 28, p. 12), computed at Chennai with one date for every city. Warren (Kala Sankalita, 1825, p. 402) describes the day as kept by bathing in sacred rivers, giving alms and offering to the ancestors; Dharmasindhu p. 2 gives the bath and gifts at the ingress, and p. 31 the Mesha punyakala, ten nadis either side. The mango pachadi, the kolam and the temple visits are popular practice.",
    "baisakhi": "Popular practice; no text read names Baisakhi. It is kept on the day, counted from sunrise to sunrise at Amritsar, in which the Sun enters sidereal Mesha, the way Lohri's Maghi is found; one date for every city, with no time. Dharmasindhu p. 2 gives the bath and gifts at the ingress, and p. 31 the Mesha punyakala, ten nadis either side. The harvest fair, the Khalsa's founding in 1699, the nagar kirtan and the bhangra are popular practice or history, outside the texts read.",
    "gangaur": "Gangaur is the popular name of the Gauri-tritiya: Gauri worshipped with Shiva on the Caitra shukla Tritiya, then rocked on a swing (Nirṇaya-sindhu p. 114, from the Devī-purāṇa; Dharmasindhu pp. 31–32; Vratarāja f. 38, a women's rite for good fortune with a night vigil). The day follows Dharmasindhu p. 9's Gauri-vrata rule: the day whose sunrise the Tritiya holds, even by a trace; two such, the later; none, the Dvitiya-joined day on which it begins. Nirṇaya-sindhu, after Mādhava, asks for at least a muhurta of Tritiya on the later day. The eighteen days of worship from the day after Holi, the clay images, the processions and the immersion are popular practice.",
    "vinayaka-chaturthi": "Popular practice as a monthly vow: the texts read give the Vinayaka-vrata on the Caitra (Dharmasindhu p. 32), Bhadrapada and Magha (Dharmasindhu p. 89) shukla Caturthis, but no text read prescribes it every month. Each shukla Caturthi is listed by the rule the site keeps for Ganesha Chaturthi (Nirṇaya-sindhu p. 47, Bṛhaspati): the later day when the Caturthi reaches its midday, otherwise the earlier, Trtiya-joined day. Dharmasindhu p. 9 reads the rule more strictly: the later day only when the Caturthi pervades the later day's whole midday alone, and the earlier day in every other case; where that gives the earlier day, dsEarlier names it.",
    "skanda-sashti": "The Bhaviṣya, through Hemādri in the Vratarāja (f. 108), makes every Shashthi Skanda's, in both fortnights, kept with fruit or a night meal and no oil; this list gives each shukla Shashthi. The day is the Shashthi joined to the Panchami (Vratarāja f. 108; Nirṇaya-sindhu p. 48; Dharmasindhu pp. 9–10): the day on which it begins between sunrise and sunset, or, begun at night, the first day whose sunrise it holds. Reading the joining as by day is ours. The Karttika one is the Vratarāja's own heading.",
    "kalashtami-monthly": "Some keep a fast for Kalabhairava on every dark Ashtami (Dharmasindhu p. 10). Dharmasindhu decides each one as it does the Bhairava-jayanti: the Ashtami covering midday; covering both middays, the earlier day; when the earlier day has it only at pradosha and the later only at midday, the pradosha day. variantDate gives the other view Dharmasindhu reports, where it differs. The amanta Karttika one is Kaal Bhairav Jayanti, with its own night vigil.",
    "rang-panchami": "Popular practice; no text read names Rang Panchami or gives its day. Dharmasindhu p. 95 says that ordinary people now keep the colour festival up to the dark Panchami, though its own day for the colours is the dark Dvitiya. Swamikannu Pillai's Indian Ephemeris (1922, pp. 65–66) and the Poona Gazetteer (1885, p. 293) describe the Panchami as the day colours are thrown and the Holi ends. The day here is our rule: the first day whose sunrise holds the dark Panchami after Holi, else the day in which it begins. The Gair and the processions are popular practice.",
    "cheti-chand": "Popular practice; no text read names Cheti Chand or Udero Lal. One date for every city, computed at Ahmedabad: the first day whose sunset falls in the Caitra shukla Dvitiya, else the first day whose sunrise holds it; the first day of Chet, when the young moon is first seen (our reading). Dharmasindhu p. 31 gives a worship of the young moon at nightfall on this Dvitiya, a different vow. The Sind gazetteers describe the Sindhi new year kept at the riverside and at Uderolal's fair (Aitken 1907 p. 206; Imperial Gazetteer 1908 p. 411), and Kincaid (1925, p. 12) the tradition that Udero Lal was born on it. When the Dvitiya begins inside the earlier evening's pradosha, that day is also given, as some keep it; in an adhika-Caitra year the day in the first Caitra is also given. The Behrana Sahib and the processions are popular practice.",
    "sheetala-ashtami": "Popular practice; no text read gives the Caitra Sheetala Ashtami or Saptami. The day here is our rule: the first day whose sunrise holds the dark Ashtami after Holi (the amanta Phalguna krishna, the purnimanta Caitra krishna), else the day in which it begins; the worship is at dawn with food cooked the day before. Two variants are given: the Saptami by the same rule, kept in some regions and families, and in Rajasthan a move off a Sunday, Tuesday or Saturday to the nearest earlier other day. Jaipur's 1903 census lists Sitla Ashtami among its March festivals (p. 356). The texts' only Shitala vow is the Shravana (purnimanta Bhadrapada) dark Saptami (Vratarāja f. 110; Nirṇaya-sindhu p. 183), not this day. The stale food, the Saptami and the weekday shift are popular practice, and no health result is claimed.",
    "kali-puja": "Popular practice; no text read names Kali Puja (Shyama Puja) or gives its day. The day here is our rule, drawn from the days observed: the night whose nishitha, the middle muhurta of the night, falls in the Dipavali Amavasya (amanta Ashvina, purnimanta Kartika); if the Amavasya covers both nights' nishitha, the night with more of it is kept, and the earlier if they are equal; if it covers neither, the later night, which holds the Amavasya at pradosha (our reading). pujaWindow is that nishitha within the Amavasya. The texts read give this night other rites: Lakshmi worshipped at pradosha (Tithi-tattva pp. 185–186; Nirṇaya-sindhu pp. 299–300), and the women of the town driving Alakshmi out of their house-yards after midnight (Dharmasindhu p. 77). None of them names Kali or Shyama, and the image, the offerings and the night's rites are practice.",
    "ahoi-ashtami": "Popular practice; no text read gives Ahoi Ashtami, its day or its story. The day here is our rule, drawn from the days observed: the dark Ashtami of the nija amanta Ashvina (purnimanta Kartika), on the day whose pradosha, the three muhurtas after sunset, falls in it; if it covers both days' pradosha, the day with more of it is kept, and the earlier if they are equal; if it covers neither, the later day, whose sunrise holds it (our reading). The fast is broken at dusk on sighting the stars, or after moonrise in some families; no text read gives a star-sighting time, so sunset and moonrise are the times given. Dharmasindhu p. 76 has only a bath in Radha-kunda on this Ashtami, for those who live near Mathura.",
    "vaikuntha-ekadashi": "Popular practice; no text read gives the day. Swamikannu Pillai's Indian Ephemeris (1922, p. 64) names it under Pausha shukla 11, a lunar placement, but the days observed follow the solar month, so the rule takes the shukla Ekadashi whose Smarta fast falls in Margazhi at Chennai, for every city. Each city keeps it on its own Ekadashi day, the Smarta fast, with the Vaishnava fast as a variant where the two differ. A calendar year can hold none, one or two.",
    "navaratriDays": "Navaratra names a worship set in nine tithis, the Pratipada to the Navami (DS p. 65). Each day's worship goes with the tithi at its sunrise (our reading of DS p. 66); a tithi touching two sunrises is worshipped on both days and one touching none on the day it falls in, so the Navaratri runs eight, nine or ten days. Some keep only eight worships when a day is lost (DS p. 66). The first day is the kalasha-sthapana day.",
    "durgashtami": "Mahashtami: the Ashtami at sunrise joined to the Navami, never one touched by the Saptami however slightly, even with Mula (NS p. 263, DS p. 69). Especially praised on a Tuesday (DS). Bhadra does not bar the worship (Devī-purāṇa, NS p. 264). Those with sons do not fast on it (DS p. 69; NS p. 265).",
    "mahanavami": "The Navami joined to the Ashtami is taken for the worship and the fast when it covers three muhurtas before that day's sunset (NS pp. 272–273, DS p. 69), so Durgashtami and Mahanavami often fall on one day. The animal bali is on the Dashami-joined day (DS p. 69).",
    "sandhiPuja": "The worship at the junction: the last ghatika of the Ashtami and the first of the Navami, by day or by night (DS p. 69), the 48 minutes centred on the junction. A junction at midday or in the afternoon puts the Ashtami and Navami worships on one day, done together with it.",
    "chaitra-navaratri": "The Vasantika Navaratri begins on the Caitra shukla Pratipada by the Sharadiya rule (NS p. 113, DS p. 31), ten-ghatika window included (our reading of 'as for the Sharadiya'). The Ashtami (Bhavani's birth) is taken joined to the Navami (NS p. 118, DS p. 33), and the Navaratri ends on the Navami by the Mahanavami rule (DS p. 34), which can fall a day before Rama-navami. newYearDate is the Pratipada at sunrise, the earlier when at sunrise on both days or neither (DS p. 31): Gudi Padwa and Ugadi.",
    "ramanavami": "Rama was born on the Caitra shukla Navami at midday, under Punarvasu, with Cancer rising (Agastya-saṃhitā, NS pp. 118–119; DS p. 33). The fast is kept on the Navami covering midday and the arghya given then; pujaWindow is midday, the 3rd fifth of the daytime, while the Navami runs.",
    "holiColours": "colours is the morning after the fire: Dharmasindhu p. 95 has the bath and the salutation of the Holika's ground or ash in the morning after the night's festival ('evam ratrau holikotsavam krtva pratah'; tying it to this morning is our reading), the rite behind the name Dhulivandana, popularly Dhulandi. Dharmasindhu puts the sprinkling of vermilion and scented powders on the dark Dvitiya and says that people in its day kept the festival up to the Panchami; no text cited here puts the colours on this morning.",
    "vasantotsava": "The spring festival on the dark Pratipada after the Holika Purnima (NS p. 345, DS p. 95): a bath, the salutation of the Holika fire's ground or ash, and mango blossoms eaten with sandal paste. DS puts the sprinkling of coloured powders on the next day, the dark Dvitiya, and says that people now keep it up to the Panchami. Neither text has colour play on the Pratipada. DS avoids the Holika day and the day after it for auspicious acts (p. 95).",
    "vijayadashami": "Ashvina shukla Dashami. pujaWindow is the afternoon (the 4th fifth of the daytime, our reading) while the Dashami runs. Aparajita puja is done in the afternoon facing north-east (Skanda via Hemādri, NS p. 283). The Vijaya moment is just after twilight as the first stars appear (Nārada, p. 284); not computed.",
    "holika-dahana": "The Phalguna Purnima, lit at night, never by day (Dharmasindhu p. 94). Bhadra's tail is the last 3 ghatikas of the tithi's 3rd prahara and its face the first 5 of the 4th (DS pp. 94–95, MC 1.44); the tail is auspicious, the face never used. Nirṇaya-sindhu is stricter, lighting only after Bhadra ends (p. 343); its day is variantDate where it differs. Not in an adhika month (NS p. 344). Ranga-panchami: Dharmasindhu p. 95 says that people now keep the colour festival up to the dark Panchami; the name and a day rule are not in the texts read (our reading: the Panchami current at sunrise).",
}  # fmt: skip
# panchang-yogas.md s1
BHADRA_PARTS = {
    "face": {
        "name": "Bhadra's face",
        "note": "The first 5 ghatis of one prahara (an eighth of the tithi), by tithi; bad.",
        "source": "Muhūrta-cintāmaṇi 1.44, pp. 35–36",
    },
    "tail": {
        "name": "Bhadra's tail",
        "note": "The last 3 ghatis of another prahara; auspicious.",
        "source": "Muhūrta-cintāmaṇi 1.44, pp. 35–36",
    },
    "dayNight": "Muhūrta-cintāmaṇi adds that a Bhadra in the second half of a tithi is auspicious by day, and one in the first half at night (MC 1.44, pp. 35–36). The avoid list does not apply this yet.",
}
FESTIVAL_CAUTIONS = {
    "first_16_nadis": "The Pratipada's first sixteen nadis (6 h 24 min)",
    "chitra": "The Moon in Chitra",
    "vaidhriti": "Vaidhriti yoga",
    "ghatika_margin": "The day the rule gives if the Shashthi's start or end moves by one ghatika (24 minutes)",
    "popular_sunrise_day": "Guru Pūrṇimā is also commonly kept on this day; popular practice",
    "no_krittika_sunset": "Krittika falls at neither sunset; Karthigai Deepam is also kept on this day; popular practice",
    "krittika_margin": "The day Karthigai Deepam may fall on if Krittika begins or ends one ghatika (24 minutes) earlier or later; our reading",
    "practice_margin_next_day": "Pongal is also commonly kept on this day; popular practice",
    "tithi_ghatika_margin": "The day the rule gives if the tithi's start or end moves by one ghatika (24 minutes)",
    "pradosha_start": "Cheti Chand is also kept on this day; popular practice",
    "adhika_month": "The day in the first (adhika) Caitra of this year; popular practice",
    "saptami": "Kept on the Saptami in some regions and families; popular practice",
    "rajasthan_weekday": "In Rajasthan the worship moves off a Sunday, Tuesday or Saturday; popular practice",
    "near_boundary": "A close call: had the tithi begun or ended five minutes differently, the rule would give this day.",
}
SANKASHTI_NOTE = (
    "Krishna paksha, by common practice; the texts read do not state the fortnight. Moonrise "
    "is the visible rise, the Moon's upper limb with refraction (our convention; the texts "
    "do not say). On a Tuesday it is popularly Angaraki: a Chaturthi on a Tuesday 'gives "
    "fruit like the equinox' (Śātātapa, Nirṇaya-sindhu p. 73); the name was not found in the "
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
        "source": "Muhūrta-cintāmaṇi 1.55, p. 49 (commentary, quoting Vivāha-vṛndāvana)",
        "note": "MC counts the horas from the start of the weekday; Vivāha-vṛndāvana from sunrise, which is used here. The 24th runs to the next sunrise.",
    },
}
PURNIMA_EARLIER_NOTE = (
    "Family custom (kula-dharma) keeps the Purnima vrata on this earlier, Caturdashi-joined day; "
    "the Dharmasindhu accepts it only when the Caturdashi lasts under 18 nadis (7 h 12 min) after "
    "that day's sunrise (DS p. 20), so earlierDate is given only then."
)
# festivals.md s26.2 (decision 26): a popular name, with the texts' other days
PURNIMA_NAMES = {
    "buddha": ("Buddha Purnima (popular name)", "The Vaishakha Purnima. No text read ties the Buddha to it: Dharmasindhu puts the Buddha avatara's birth on the Ashvina shukla Dashami, in the evening (p. 32), and Nirṇaya-sindhu gives that day, Jyeshtha shukla Dvitiya or Pausha shukla Saptami, settling them by the difference of kalpas (pp. 116–117)", "Dharmasindhu p. 32; Nirṇaya-sindhu pp. 116–117"),
}  # fmt: skip
# festivals.md s26.4: the ten yogas of Ganga-dashahara (NS p. 144, DS p. 38)
GANGA_YOGAS = {
    "jyeshtha": "The month of Jyeshtha",
    "shukla": "The bright fortnight",
    "dashami": "The Dashami",
    "wednesday": "Wednesday",
    "hasta": "Hasta",
    "vyatipata": "Vyatipata yoga",
    "gara": "Gara karana",
    "ananda": "Ananda (Wednesday with Hasta)",
    "moon_kanya": "The Moon in Kanya",
    "sun_vrishabha": "The Sun in Vrishabha",
}
# observances.md s6
AMAVASYA_NAMES = {
    "mahalaya": ("Mahalaya Amavasya", "The last day of the Mahalaya fortnight, the dark fortnight after the Bhadrapada full moon", "Nirṇaya-sindhu p. 215"),
    "magha": ("Magha Amavasya", "A yugadi day: the new moon that ends amanta Magha", "Nirṇaya-sindhu p. 341"),
    "mauni": ("Mauni Amavasya (popular name)", "The new moon inside purnimanta Magha (amanta Pausha); the texts read do not use the name. Nirṇaya-sindhu asks for silence during the Magha bath, which this new moon falls inside", "Nirṇaya-sindhu p. 321 (silence in the Magha bath)"),
    "somavati": ("Somavati Amavasya (Monday)", "A Monday Amavasya 'gives fruit like the equinox'; the commentary says 'somavari amavas'", "Nirṇaya-sindhu p. 73 (Śātātapa, Vyāsa)"),
    "bhauma": ("Bhauma Amavasya (Tuesday)", "On a Tuesday Amavasya, bathing in the Ganga gives the fruit of a thousand cows", "Nirṇaya-sindhu p. 73 (Śātātapa)"),
    "shani": ("Shani Amavasya (Saturday)", "Popular observance; no classical source found", None),
}  # fmt: skip
# Shown labelled popular, as the English page does (the lead, 16 Oct 2026).
AMAVASYA_POPULAR = {"mahalaya": "Sarva Pitru Amavasya"}
SHRADDHA_NOTE = (
    "Hemādri makes the kutapa primary for households without sacred fires; Hārīta's rule by "
    "Vedic branch decides equal coverage (Nirṇaya-sindhu pp. 82, 86–87). Kshaya and vrddhi "
    "here mean the Amavasya touches no sunrise or two (our reading)."
)
EKADASHI_NOTE = (
    "A tithi runs long when it is still current at the sunrise after its own day: Ekādaśī at "
    "the second day's sunrise, Dvādaśī at the third's, counting from the first Ekādaśī day "
    "(our reading of Nirṇaya-sindhu pp. 59–62)."
)
ASPECTS = {
    "source": {
        "text": "Bṛhaj-jātaka",
        "verse": "2.13",
        "edition": "Varāhamihira, translated by Swami Vijñānānanda, 1912",
        "page": "48–49",
    },
    "scope": (
        "Full aspects only. Bṛhaj-jātaka 2.13 also gives partial aspects (a quarter on the 3rd "
        "and 10th, a half on the 5th and 9th, three quarters on the 4th and 8th), not shown "
        "here. Bṛhaj-jātaka 2.13 and Jātaka-pārijāta 2.30–31 name no aspect for Rahu or Ketu."
    ),
}
# PD 6.5: "There are some who declare that there is no Kemadruma where ..."
# PD 26.22-23 (1937, pp. 294-295), quoted as printed; no predictions of our own.
SADE_SATI_PHASES = {
    "rising": (12, "When Saturn is in the 12th house, the native will be wearied by being engaged in a worthless and fruitless business. He will be robbed of his moneys by his enemies. His wife and sons will suffer from sickness.", "26.23", "295"),
    "peak": (1, "During Saturn's transit through the Janmarasi, the native will suffer from disease; he will perform funeral rites;", "26.22", "294–295"),
    "setting": (2, "in the 2nd house he will suffer trouble to wealth and children", "26.22", "294–295"),
}  # fmt: skip
YOGA_CHECKS = {
    "moon_in_kendra": "The Moon is in a kendra from the lagna",
    "planet_with_moon": "A graha is with the Moon",
    "planet_in_kendra_from_moon": "A graha is in a kendra from the Moon",
}
DIGNITY_NOTES = {
    "node_debilitation_our_reading": "Debilitated as the 7th sign from its exaltation (our reading; BPHS names no sign)",
    "node_own_sign_by_some": "Own sign according to some (BPHS Daśā-phala v.36); the main view is Aquarius for Rahu, Scorpio for Ketu",
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
    "amrita_siddhi": ("Siddhi (amrta) yoga", "Nārada, quoted in Muhūrta-cintāmaṇi 1.21 commentary, p. 20. Avoided on its excluded tithi (Muhūrta-cintāmaṇi 1.20–21, pp. 19–20) and for its act: Tuesday-Ashwini for entering a house, Saturday-Rohini for a journey and Thursday-Pushya for a marriage (Muhūrta-cintāmaṇi 1.22, p. 20); it never lifts Bhadra, Vyatipata or Vaidhriti (Muhūrta-cintāmaṇi 1.42 commentary, p. 35)", "good"),
    "visha": ("Visha yoga", "Muhūrta-cintāmaṇi 1.20–21, pp. 19–20: a siddhi pair on its excluded tithi (Daivajña-manohara calls these visha)", "avoid"),
    "sarvartha_siddhi": ("Sarvartha Siddhi", "Muhūrta-cintāmaṇi 1.28–29, p. 22, main reading (a footnoted variant reads Anuradha for Purva Phalguni on Friday)", "good"),
    "siddha": ("Siddha", "Muhūrta-cintāmaṇi 1.4, Kaśyapa in the commentary, p. 12", "good"),
    "marana": ("Marana (Mrtyu)", "Muhūrta-cintāmaṇi 1.30, p. 23", "avoid"),
    "utpata": ("Utpata", "Muhūrta-cintāmaṇi 1.30, p. 23: the first of each weekday's run of four nakshatras; 'its effect is like its name'", "avoid"),
    "kana": ("Kana", "Muhūrta-cintāmaṇi 1.30, p. 23: the third of the run. Monday's is Abhijit, the last quarter of Uttara Ashadha and the first fifteenth of Shravana (Muhūrta-mārtaṇḍa p. 139)", "avoid"),
    "siddhi": ("Siddhi (weekday and nakshatra)", "Muhūrta-cintāmaṇi 1.30, p. 23: the fourth of the run; 'its effect is like its name'", "good"),
    "mahapata": ("Mahapata (equal declinations)", "Muhūrta-cintāmaṇi 1.34 commentary, p. 30: the moment the Sun's and Moon's declinations are equal, computed as in Sūrya-siddhānta ch. 11, pp. 273–280: Vyatipata-type with longitudes summing to about 180 degrees and declinations equal, Vaidhriti-type summing to about 360 and opposite; its half-duration, per Sūrya-siddhānta 11.14, p. 277, is sixty times the half-sum of the two discs over the difference of the daily motions, in nadis; near the equator it can occur twice, near a solstice not at all (Sūrya-siddhānta 11.19, p. 279). Nārada, quoted in MC, avoids the whole day", "avoid"),
    "ravi": ("Ravi yoga", "Muhūrta-cintāmaṇi 1.27, p. 22: the Moon's nakshatra the 4th, 6th, 9th, 10th, 13th or 20th from the Sun's, counted inclusively (our reading); it 'destroys a host of defects'", "good"),
    "dagdha": ("Dagdha", "Muhūrta-cintāmaṇi 1.5, Nārada in the commentary, p. 13", "avoid"),
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
    "dakshinayana": "The Sun's southern course (MC 13.1; for a tonsure MC 5.26, 5.29)",
    "weekday_home": "Sunday or Tuesday: no house entry (MC 13.4)",
    "month_mundan": "Caitra: no tonsure (MC 5.29)",
    "nakshatra_mundan": "Not one of the twelve tonsure stars (MC 5.29; Vasiṣṭha; DS p. 137)",
    "tithi_mundan": "Not tithi 2, 3, 5, 7, 10, 11 or 13 (MC 5.29; DS p. 137)",
    "weekday_mundan": "Not Wednesday, Thursday, Friday, or Monday in the bright fortnight (MC 5.29; Parāśara)",
    "lagna_mundan": "The lagna not in a benefic's sign (MC 5.29; Kaśyapa)",
    "navamsa_mundan": "The lagna's navamsa not in a benefic's sign (MC 5.29)",
    "house_8_mundan": "A planet other than Venus in the 8th (MC 5.29; Parāśara)",
    "kendra_malefic_mundan": "The waning Moon, Mars, Saturn or the Sun in a kendra (MC 5.30)",
    "birth_star": "The child's birth star (DS p. 137; Kaśyapa allows it for a Vedic tonsure)",
    "birth_month": "The child's birth month (Rājamārtaṇḍa, MC p. 190)",
    "lagna_8th_from_birth_mundan": "The lagna 8th from the child's birth lagna or Moon sign (MC 5.29)",
    "eldest_jyeshtha": "Jyeshtha, for an eldest child (Ratnamālā, MC 5.33 commentary)",
    "selling_star": "A selling star, barred for buying: the three Purvas, Vishakha, Krttika, Ashlesha, Bharani (MC 2.16–17)",
    "riding_weekday": "Not a riding weekday: Thursday, Monday, Sunday, Friday or Wednesday (the Vyavahāroccaya in MC 2.18 commentary)",
    "not_buying_star": "Not one of the six buying stars: middling for buying (MC 2.16, p. 62, with the commentary, p. 63)",
    "middling_month_home": "Kartika or Margashirsha: middling, for necessity (Nārada in MC 13.1)",
    "sun_sign_home": "The Sun in Cancer, Virgo or Aquarius (Guru in MC 13.1)",
    "jupiter_venus_state": "Jupiter or Venus set, old or infant (MC 1.46–48, 5.27)",
    "jupiter_sign": "Jupiter in Leo or Capricorn (MC 1.48)",
    "movable_lagna_home": "Movable lagna (MC 13.4)", "movable_navamsa": "Movable navamsa (MC 13.4 commentary)",
    "house_4_8_occupied": "A planet in the 4th or 8th (MC 13.4)",
    "moon_1_6_12": "The Moon in the 1st, 6th or 12th (Vasiṣṭha in MC 13.3–4)",
    "pot_chakra": "Pot chakra: the Moon's star 1st-5th or 14th-21st from the Sun's (MC 13.6; DS p. 242)",
    "door_star": "Star not of the door's quarter: seven to each quarter, from Krttika east, Magha south, Anuradha west and Dhanishtha north (MC 11.33 commentary, p. 353; MC 13.1)",
    "door_tithi": "Tithi not of the door's class (MC 13.5)",
    "door_sun": "The Sun not on the left for the door (MC 13.4–5)",
    "utpata_yoga": "Utpata yoga (MC 1.30)", "kana_yoga": "Kana yoga (MC 1.30)",
    "mahapata": "Mahapata, equal declinations (MC 1.34)", "siddhi_yoga": "Siddhi yoga (MC 1.30)",
    "visha_yoga": "Visha yoga: a siddhi pair on its excluded tithi (MC 1.20–21)",
    "siddhi_pair_act_ban": "Siddhi pair avoided for this act (MC 1.22)",
    "amavasya": "Amavasya", "rikta_tithi": "Rikta tithi (4th, 9th, 14th)", "ashtami": "Ashtami",
    "marana_yoga": "Marana yoga", "dagdha_yoga": "Dagdha yoga", "moon_8th": "Moon in the 8th",
    "chandrashtama": "Chandrashtama: the Moon 8th from the birth Moon (Phaladīpikā 26.2, 26.12)",
    "disha_shool": "Disha shool (Nārada and Vasiṣṭha in the MC 11.9 commentary)",
    "disha_shool_first_leg": "Disha shool on the first leg (Nārada and Vasiṣṭha in the MC 11.9 commentary)", "bad_tara": "Inauspicious tara",
    "janma_tara": "Janma tara", "panchaka": "Panchaka", "malefic_1st": "Malefic in the 1st",
    "malefic_7th": "Malefic in the 7th", "graha_8th": "Graha in the 8th",
    "malefic_4th": "Malefic in the 4th", "lagna_8th_from_birth": "Lagna 8th from birth",
    "bad_choghadiya": "Inauspicious choghadiya", "char_choghadiya": "Char choghadiya",
    "moon_from_birth_moon": "Moon 4th or 12th from the birth Moon, or 2nd, 5th or 9th outside the bright fortnight (Phaladīpikā 26.2; MC 4.4)",
    "moon_good_from_birth_moon": "Moon 1st, 3rd, 6th, 7th, 10th or 11th from the birth Moon, or 2nd, 5th or 9th in the bright fortnight (Phaladīpikā 26.2; MC 4.4)",
    "travel_best_tithi": "The dark Pratipada, the best tithi for travel (MC 11.9 commentary)",
    "nakshatra_unfavoured": "Nakshatra not favoured for this act",
    "tithi_unfavoured": "Tithi not favoured for this act",
    "weekday_unfavoured": "Weekday not favoured for this act", "adhika_masa": "Adhika masa",
    "pitru_paksha_practice": "Pitru Paksha: many families avoid new purchases; the texts read give no such rule (popular practice)", "moon_behind": "Moon behind (Chandra vasa)",
    "moon_left": "Moon on the left", "moon_ahead": "Moon ahead or on the right",
    "yogini_ahead": "Yogini ahead or on the left (MC 11.31)", "yogini_behind": "Yogini behind or on the right (MC 11.31)",
    "kharmas": "Kharmas", "amrita_siddhi": "Siddhi (amrta) yoga", "sarvartha_siddhi": "Sarvartha Siddhi",
    "ravi_yoga": "Ravi yoga: the Moon's star the 4th, 6th, 9th, 10th, 13th or 20th from the Sun's (MC 1.27)",
    "adhika_month_annaprashan": "An adhika month: no first rice (DS pp. 4, 135)",
    "tithi_annaprashan": "Not a first-rice tithi: the bright 2nd, 3rd, 5th, 7th, 10th or 13th (MC 5.17 commentary; DS p. 135)",
    "weekday_annaprashan": "Not a first-rice weekday: Monday, Wednesday, Thursday or Friday (MC 5.17)",
    "nakshatra_annaprashan": "Not one of the sixteen first-rice stars (DS p. 135)",
    "forenoon_annaprashan": "Not the forenoon, sunrise to midday (Nārada, MC 5.17 commentary)",
    "vishti_annaprashan": "Vishti, whatever its residence, for its whole span (DS p. 135; our reading)",
    "yoga_annaprashan": "Vaidhriti, Vyatipata, Ganda, Atiganda, Vajra, Shula or Parigha, for its whole span (DS p. 135)",
    "lagna_annaprashan": "Aries, Scorpio or Pisces rising (MC 5.17)",
    "house_10_annaprashan": "A planet in the 10th (MC 5.18)",
    "malefic_annaprashan": "A malefic in the 1st, 4th or 7th (MC 5.18)",
    "moon_6_8_annaprashan": "The Moon in the 6th or 8th (MC 5.18)",
    "guru_7_8_9_annaprashan": "Venus in the 7th, Mars in the 8th or Mercury in the 9th (Guru in MC 5.18 commentary, p. 180)",
    "lagna_8th_annaprashan": "The lagna 8th from the child's birth Moon sign or lagna (MC 5.17)",
    "navamsa_8th_annaprashan": "The navamsa 8th from the child's birth Moon sign or lagna (MC 5.17; Kaśyapa)",
    "month_of_life": "Not a first-rice month for the child: a boy's 6th, 8th, 10th or 12th or the end of the first year, a girl's 5th, 7th, 9th or 11th (MC 5.17; DS p. 135)",
    "sun_aquarius_akshararambh": "The Sun in Aquarius: no first letters (DS p. 138)",
    "hari_sleeps": "Vishnu asleep, from the Devashayani Ekadashi to the Karka sankranti (Mārkaṇḍeya in MC 5.37 commentary)",
    "tithi_akshararambh": "Not a first-letters tithi: 2, 3, 5, 10, 11 or 12, outside the dark fortnight's last three days (MC 5.37; DS p. 138)",
    "weekday_akshararambh": "Not a first-letters weekday: Monday, Wednesday, Thursday or Friday (MC 5.37)",
    "nakshatra_akshararambh": "Not one of MC 5.37's ten first-letters stars",
    "lagna_akshararambh": "Not Taurus, Gemini, Virgo, Sagittarius or Pisces rising (MC 5.37)",
    "house_8_akshararambh": "A planet in the 8th (Nṛsiṃha and Śrīdhara in MC 5.37 commentary)",
    "fifth_year": "Not the child's 5th year (MC 5.37; DS p. 138)",
    "kuyoga_lifted": "A bad weekday yoga lifted by a Ravi or siddhi yoga, or by a favourable Moon from the birth Moon (MC 1.41–42)",
    "nakshatra_gandanta": "Nakshatra gandanta: within 2 ghatikas of the Ashlesha-Magha, Jyeshtha-Mula or Revati-Ashvini junction (MC 6.41; SS 11.22)",
    "nakshatra_junction_near": "Nakshatra junction within 4 ghatikas, the commentary's middling fault (MC 6.41)",
    "nakshatra_junction_quarter": "Nakshatra junction quarter: the last quarter of Ashlesha, Jyeshtha or Revati or the first of Magha, Mula or Ashvini (SS 11.21)",
    "lagna_gandanta": "Lagna gandanta: half a ghatika either side of the Cancer-Leo, Scorpio-Sagittarius or Pisces-Aries boundary (MC 6.41)",
    "tithi_gandanta": "Tithi gandanta: one ghatika either side of the end of the 5th, 10th or 15th tithi (MC 6.41)",
    "lagna_lord_strong": "Lagna lord strong", "benefic_kendra": "Benefic in a kendra",
    "abhijit": "Abhijit muhurta", "movable_lagna": "Movable lagna", "fixed_lagna": "Fixed lagna",
    "favoured_hora": "Favoured hora", "malefic_hora": "Mars or Saturn hora",
}  # fmt: skip
VETOES = {
    "rahu_kalam", "yamaganda", "gulika", "durmuhurta", "bad_yoga_window", "bhadra_earth",
    "amavasya", "rikta_tithi", "ashtami", "marana_yoga", "dagdha_yoga", "moon_8th",
    "disha_shool", "visha_yoga", "siddhi_pair_act_ban", "bhadra_face",
    "utpata_yoga", "kana_yoga", "mahapata", "adhika_masa_home", "month_home", "dakshinayana", "weekday_home", "month_mundan",
    "nakshatra_mundan", "tithi_mundan", "weekday_mundan", "lagna_mundan", "house_8_mundan",
    "kendra_malefic_mundan", "navamsa_mundan", "birth_star", "birth_month", "lagna_8th_from_birth_mundan",
    "eldest_jyeshtha", "selling_star", "riding_weekday",
    "sun_sign_home", "jupiter_venus_state", "jupiter_sign", "movable_lagna_home", "movable_navamsa",
    "house_4_8_occupied", "moon_1_6_12", "pot_chakra", "door_star", "door_tithi", "door_sun",
    "nakshatra_gandanta", "lagna_gandanta", "tithi_gandanta",
    "adhika_month_annaprashan", "tithi_annaprashan", "weekday_annaprashan", "nakshatra_annaprashan", "forenoon_annaprashan", "vishti_annaprashan", "yoga_annaprashan", "lagna_annaprashan", "house_10_annaprashan", "malefic_annaprashan", "moon_6_8_annaprashan", "guru_7_8_9_annaprashan", "lagna_8th_annaprashan", "navamsa_8th_annaprashan", "month_of_life", "sun_aquarius_akshararambh", "hari_sleeps", "tithi_akshararambh", "weekday_akshararambh", "nakshatra_akshararambh", "lagna_akshararambh", "house_8_akshararambh", "fifth_year",
}  # fmt: skip
NOTES = {"pitru_paksha_practice", "kuyoga_lifted"}  # shown, never scored
CURRENT_PRACTICE = "Current practice; no classical source"
MUHURTA_RULE_NOTES = {
    **dict.fromkeys(("bad_choghadiya", "char_choghadiya"), CURRENT_PRACTICE),
    # travel.md (the lead's decisions of 15 Oct 2026)
    **dict.fromkeys(
        ("moon_behind", "moon_left", "moon_ahead"),
        "Current practice; no classical source. MC 11.36 (1945 printing, p. 359) gives a "
        "different rule: with the Sun and the Moon both in the northern course go north or "
        "east, both in the southern go west or south; if their courses differ, travel by day "
        "in the Sun's direction and by night in the Moon's.",
    ),
    # panchang-yogas.md (the lead's decisions of 15 Oct 2026)
    **dict.fromkeys(
        ("utpata_yoga", "marana_yoga", "kana_yoga", "dagdha_yoga", "visha_yoga"),
        "A Ravi or siddhi yoga at the same moment lifts it (MC 1.27, 1.42); a siddhi pair "
        "turned to visha lifts nothing. In the personal search a favourable Moon from the "
        "birth Moon lifts it too (MC 1.41). MC 1.41–42 records other views, not applied: "
        "some lift these yogas after the first yama, some hold them only for travel, and "
        "some lift them with a pure lagna.",
    ),
    **dict.fromkeys(
        ("bhadra_earth", "bad_yoga_window"),
        "Never lifted by a good yoga (MC 1.42 commentary, p. 35). For an unavoidable act, "
        "Bhadra, Tuesday, Vyatipata, Vaidhriti, the pratyari star and the birth star are "
        "acceptable after midday (the same commentary); not applied.",
    ),
    **dict.fromkeys(
        ("yogini_ahead", "yogini_behind"),
        "In front or on the left the Yogini is not commended (MC 11.31, p. 348); on the "
        "right or behind she is (MC 11.31, p. 348, with the commentary, p. 349). Popular "
        "practice reverses left and right. A minor factor: the commentary weighs it mainly "
        "in war journeys (MC 11.32 commentary, p. 352).",
    ),
}
SUPPORTS = {
    "amrita_siddhi", "sarvartha_siddhi", "lagna_lord_strong", "benefic_kendra", "abhijit",
    "moon_ahead", "yogini_behind", "char_choghadiya", "movable_lagna", "fixed_lagna",
    "favoured_hora", "siddhi_yoga", "bhadra_tail", "bhadra_day_night",
    "moon_good_from_birth_moon", "travel_best_tithi", "ravi_yoga",
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
    "same_nakshatra_same_pada": "Same nakshatra and pada: held fatal (Nārada; MM v.6)",
    "tara_clear_same_sign": "Same Moon sign: no tara fault (MC 6.36 commentary)",
    "sign_lords_friendly": "The Moon-sign lords are friends (MC 6.33, p. 256)",
    "navamsha_lords_friendly": "The Moons' navamsha lords are friends (MC 6.33)",
    "same_sign_lord": "Both Moon signs have the same lord (MC p. 256)",
    "tara_pure_both_ways": "Tara is pure both ways (Rājamārtaṇḍa, in MC p. 255)",
    "navamsha_lords_friendly_strength_not_assessed":
        "The navamsha lords are friends, but their strength (MC p. 256) is not assessed",
    "moon_uncertain_birth_time_unknown": "Birth time unknown and the Moon changed sign or star that day",
    "our_reading_of_bjs": "Vashya groups and points are our reading of Bṛhaj-jyotiḥsāra (1892)",
    "vashya_group_uncertain": "The birth-star pada spans 15 degrees of Sagittarius or Capricorn, so the vashya group is open",
    "yoni_enmity_opposite_gender": "Yoni enmity between a bride and groom of opposite yoni gender: always to be avoided (Jyotiḥprakāśa in Jyotirnibandha p. 142, v. 12). The points are unchanged",
    "yoni_enmity_same_gender": "Yoni enmity between the same yoni gender: middling, not very harmful (Jyotiḥprakāśa in Jyotirnibandha p. 142, v. 12). The points are unchanged",
}  # fmt: skip
for _rid in ("same_sign_lord", "sign_lords_friendly", "tara_pure_both_ways"):
    MATCHING_NOTES[f"{_rid}_but_nadi_dosha"] = MATCHING_NOTES[_rid] + ", but nadi is not clear"


# Eclipses (contract 7r; research's grahana.md, adopted by the lead 17 Oct 2026).
ECLIPSE_RULES = {
    "four_praharas_solar": ("For a solar eclipse no food is taken in the four praharas before the prahara holding the first contact seen at the place, the praharas being quarters of that place's day and night", "Dharmasindhu p. 28; Nirṇaya-sindhu p. 89"),
    "three_praharas_lunar": ("For a lunar eclipse no food is taken in the three praharas before the prahara holding the first contact seen at the place", "Dharmasindhu p. 28; Nirṇaya-sindhu p. 89"),
    "moon_rises_eclipsed_from_sunrise": ("When the Moon rises eclipsed, no food is taken through that day, from its sunrise", "Dharmasindhu p. 28; Nirṇaya-sindhu p. 89"),
    "four_praharas_total_lunar": ("Some give four praharas for a total lunar eclipse and three for a partial one", "Dharmasindhu p. 28"),
    "last_contact": ("The vedha ends with the bath after the last contact seen at the place", "Dharmasindhu p. 26; Nirṇaya-sindhu p. 89"),
    "next_clear_sunrise": ("When the Sun sets eclipsed, the vedha ends with the bath at its next rising, when its disc is clear", "Dharmasindhu p. 28; Nirṇaya-sindhu p. 89"),
    "next_clear_moonrise": ("When the Moon sets eclipsed, the vedha ends with the bath at its next rising, when its disc is clear", "Dharmasindhu p. 28; Nirṇaya-sindhu p. 89"),
}  # fmt: skip
ECLIPSE_NOTES = {
    "name": "Vedha, popularly called sutak: the time before an eclipse when no food is taken",
    "penumbral_no_bite": "No shadow bite: not reckoned as a grahana (our reading of Dharmasindhu p. 26's 'fit to be seen')",
    "not_visible": "Below the horizon throughout here: an astronomical event only, with no vedha and no rites (Dharmasindhu p. 26; Nirṇaya-sindhu pp. 103–106)",
    "umbral_not_visible": "Only the penumbral phase is above the horizon here: no shadow bite is seen, so it is not reckoned (our reading of Dharmasindhu p. 26)",
    "partly_visible": "Seen only in part here: it counts for the part above the horizon (Dharmasindhu p. 26)",
    "clouds": "Clouds do not cancel it: the computed contact and release times stand (Dharmasindhu p. 26)",
    "popular_start": "Popularly, sutak is counted 12 hours before a solar and 9 hours before a lunar eclipse, from the eclipse's own first contact: for a lunar eclipse the first contact of the Earth's full shadow (the umbra), the same moment everywhere, even where the Moon rises eclipsed; for a solar eclipse the place's own first contact, even with the Sun below the horizon. That is practice, not in the texts read",
    "exemptions": "Children, the old and the sick: Dharmasindhu gives a vedha of one and a half praharas or three muhurtas (p. 28), Nirṇaya-sindhu one prahara before the eclipse's prahara (p. 90)",
    "householders": "Householders with sons do not keep the optional fast at an eclipse (Dharmasindhu p. 26)",
}  # fmt: skip


# Pancaka (contract 7s; research's pancaka.md, adopted by the lead 17 Oct 2026).
PANCAKA_BARRED = {
    "cremation": ("Cremation", "Muhūrta-cintāmaṇi 2.48, p. 84"),
    "travel_south": ("Travel to the south, Yama's quarter", "Muhūrta-cintāmaṇi 2.48, p. 84"),
    "weaving_cot": ("Weaving a cot", "Muhūrta-cintāmaṇi 2.48 with the commentary, p. 84"),
    "roofing": ("Covering a house, that is, roofing it", "Muhūrta-cintāmaṇi 2.48 with the commentary, p. 84"),
    "grass_wood": ("Gathering grass and wood, which Vasiṣṭha, Nārada and Śrīpati name", "Muhūrta-cintāmaṇi 2.48 ('and the rest') with the commentary, pp. 84–85"),
    "pillars": ("Raising a house's pillars", "Dharmasindhu p. 242"),
}  # fmt: skip
# Popular practice by the vara a pancaka begins on (the lead, 17 Oct 2026); no text gives them.
PANCAKA_NAMES = {"roga": "Rog Panchak", "raja": "Raj Panchak", "agni": "Agni Panchak",
                 "cora": "Chor Panchak", "mrtyu": "Mrityu Panchak"}  # fmt: skip
PANCAKA_NOTES = {
    "name": "Dhanishtha Panchak: the Moon from the second half of Dhanishtha through Revati, which is its passage through sidereal Aquarius and Pisces (Muhūrta-cintāmaṇi 2.48 with the commentary, p. 84; Nirṇaya-sindhu p. 943)",
    "not_from_shravana": "It does not begin at Shravana: the Muhūrta-cintāmaṇi's commentary rejects that wider span, which has no root text (p. 86)",
    "not_general": "Nothing else is barred by the Panchak in the texts read. The Muhūrta-cintāmaṇi's own marriage stars include Uttara Bhadrapada and Revati (6.53), both inside it",
    "popular_names": "Popular practice; the texts read give the Dhanishtha-panchaka no weekday names",
    "bana_names": "The five names roga, agni, raja, cora and mrtyu are the Muhūrta-cintāmaṇi's banas, a separate count from the Sun's degrees with its own weekday table (6.71–72, pp. 289–290), not the Dhanishtha-panchaka's",
    "no_name": "A Panchak beginning on a Wednesday or Thursday has no popular name",
    "start_vara": "The weekday is the vara current at the start in the chosen city, sunrise to sunrise, not the civil date (our reading). A start between midnight and sunrise keeps the previous vara, so a name can differ between cities",
    "cremation": "No cremation in the Panchak, whatever the star of the death (Muhūrta-cintāmaṇi p. 85)",
    "death": "In the Panchak both the death and the cremation are faulted (Muhūrta-cintāmaṇi p. 85, with the Brahma-purāṇa; Nirṇaya-sindhu p. 944)",
    "cannot_wait": "When the cremation cannot wait, it is done after a shanti (Muhūrta-cintāmaṇi p. 85): the effigy rite",
    "effigies_garuda": "The Garuḍa: four kusha effigies, consecrated with the stars' mantras, are laid by the body and burnt with it; after the impurity the sons perform the shantika and paushtika rites, with sesame, gold and ghee for the dead (Nirṇaya-sindhu p. 943; the Muhūrta-cintāmaṇi quotes its close, p. 86)",
    "effigies_brahma": "The Brahma-purāṇa: five kusha figures, bound with wool thread and smeared with barley paste, named Pretavaha, Pretasakha, Pretapa, Pretabhumipa and Pretaharta; the cremation after the Panchak, or that same day by this rite (Muhūrta-cintāmaṇi p. 85; Nirṇaya-sindhu p. 944). The Nirṇaya-sindhu lays them at the head, the eyes, the left side, the navel and the feet (p. 944)",
    "same_day": "The Muhūrta-cintāmaṇi's commentary has the cremation done at once, with the rite, for a death from the second half of Dhanishtha on, since the Panchak lasts long and a body is not kept overnight; for a death at the very end of Revati, after Revati (p. 85)",
    "effigy_count": "The count of effigies differs: four in the Garuḍa, five in the Brahma",
    "five_gems": "Aparārka adds the five gems for a death in the Dhanishtha-panchaka (Nirṇaya-sindhu p. 944)",
    "which_remedy": "A death in another star with the cremation in the Panchak: the effigies only. A death in the Panchak with the cremation after it: no effigies, and the shanti after the impurity (Muhūrta-cintāmaṇi p. 86)",
}  # fmt: skip


# --- Names for the Hindi lane (the lead, 16 Oct 2026) ---------------------------------------
# /hi/ pages take every name from meta and never retype one: these are the English names, and
# api/src/meta/hi.labels.json holds the reviewed Hindi. Festival names follow the site's pages.
FESTIVAL_NAMES = {
    "dipavali": "Diwali",
    "mahashivaratri": "Maha Shivratri",
    "masik-shivaratri": "Masik Shivratri",
    "ganesha-chaturthi": "Ganesh Chaturthi",
    "raksha-bandhan": "Raksha Bandhan",
    "janmashtami": "Janmashtami",
    "sharad-navaratri": "Sharad Navratri",
    "chaitra-navaratri": "Chaitra Navratri",
    "ramanavami": "Ram Navami",
    "vijayadashami": "Dussehra",
    "holika-dahana": "Holika Dahan",
    "karva-chauth": "Karwa Chauth",
    "tulsi-vivah": "Tulsi Vivah",
    "tripurotsava": "Dev Diwali",
    "vasanta-panchami": "Basant Panchami",
    "ratha-saptami": "Ratha Saptami",
    "bhishma-ashtami": "Bhishma Ashtami",
    "kalashtami": "Kaal Bhairav Jayanti",
    "dattatreya-jayanti": "Dattatreya Jayanti",
    "ganesha-jayanti": "Ganesh Jayanti",
    "holashtak": "Holashtak",
    "akshaya-tritiya": "Akshaya Tritiya",
    "parashurama-jayanti": "Parshuram Jayanti",
    "guru-purnima": "Guru Purnima",
    "durga-puja": "Durga Puja",
    "vat-savitri": "Vat Savitri",
    "ganga-dussehra": "Ganga Dussehra",
    "rath-yatra": "Rath Yatra",
    "sawan-somvar": "Sawan Somwar",
    "hariyali-teej": "Hariyali Teej",
    "kajari-teej": "Kajari Teej",
    "hartalika-teej": "Hartalika Teej",
    "nag-panchami": "Nag Panchami",
    "rishi-panchami": "Rishi Panchami",
    "anant-chaturdashi": "Anant Chaturdashi",
    "chhath": "Chhath Puja",
    "chaiti-chhath": "Chaiti Chhath",
    "hanuman-jayanti": "Hanuman Jayanti",
    "radhashtami": "Radha Ashtami",
    "onam": "Onam",
    "vishwakarma-puja": "Vishwakarma Puja",
    "karthigai-deepam": "Karthigai Deepam",
    "lohri": "Lohri",
    "vishu": "Vishu",
    "tamil-new-year": "Tamil New Year",
    "baisakhi": "Baisakhi",
    "gangaur": "Gangaur",
    "vinayaka-chaturthi": "Vinayaka Chaturthi",
    "skanda-sashti": "Skanda Sashti",
    "kalashtami-monthly": "Masik Kalashtami",
    "rang-panchami": "Rang Panchami",
    "cheti-chand": "Cheti Chand",
    "sheetala-ashtami": "Sheetala Ashtami",
    "kali-puja": "Kali Puja",
    "ahoi-ashtami": "Ahoi Ashtami",
    "vaikuntha-ekadashi": "Vaikuntha Ekadashi",
    "pongal": "Pongal",
    "magha-snana": "Magha Snana",
}
# Popular names served beside the name, as the English pages carry both (the lead, 16 Oct 2026).
FESTIVAL_POPULAR = {
    "sheetala-ashtami": "Basoda",
    "magha-snana": "Magh Mela",
    "kali-puja": "Shyama Puja",
    "vaikuntha-ekadashi": "Mukkoti Ekadashi",
}
CHHATHS = ["chhath", "chaiti-chhath"]
# Named days inside a kind's answer: id -> (name, the kinds that carry it).
FESTIVAL_DAY_NAMES = {
    "dhanteras": ("Dhanteras", ["dipavali"]),
    "narakaChaturdashi": ("Naraka Chaturdashi", ["dipavali"]),
    "lakshmiPuja": ("Lakshmi Puja", ["dipavali"]),
    "govardhan": ("Govardhan Puja", ["dipavali"]),
    "bhaiDooj": ("Bhai Dooj", ["dipavali"]),
    "colours": ("Rangwali Holi", ["holika-dahana"]),
    "vasantotsava": ("Vasantotsava", ["holika-dahana"]),
    "durgashtami": ("Durga Ashtami", ["sharad-navaratri"]),
    "mahashtami": ("Maha Ashtami", ["durga-puja"]),
    "mahanavami": ("Maha Navami", ["sharad-navaratri", "durga-puja"]),
    "newYear": ("Hindu New Year (Gudi Padwa, Ugadi)", ["chaitra-navaratri"]),
    "bodhana": ("Bodhan", ["durga-puja"]),
    "amantrana": ("Amantran", ["durga-puja"]),
    "patrikaPravesha": ("Navapatrika Pravesh", ["durga-puja"]),
    "sandhiPuja": ("Sandhi Puja", ["durga-puja", "sharad-navaratri"]),
    "visarjana": ("Durga Visarjan", ["durga-puja"]),
    "nahayKhay": ("Nahay Khay", CHHATHS),
    "kharna": ("Kharna", CHHATHS),
    "sandhyaArghya": ("Sandhya Arghya", CHHATHS),
    "ushaArghya": ("Usha Arghya", CHHATHS),
    "atham": ("Atham", ["onam"]),
    "bhogi": ("Bhogi", ["pongal"]),
    "mattuPongal": ("Mattu Pongal", ["pongal"]),
    "kanumPongal": ("Kanum Pongal", ["pongal"]),
    "maghi": ("Maghi", ["lohri"]),
    "vatPurnima": ("Vat Purnima", ["vat-savitri"]),
    "vatSavitriVrat": ("Vat Savitri Vrat", ["vat-savitri"]),
    "sakatChauth": ("Sakat Chauth", ["sankashti"]),
    "vaikunthaEkadashi": ("Vaikuntha Ekadashi", ["ekadashi"]),
    "gitaJayanti": ("Gita Jayanti", ["ekadashi"]),
}
OBSERVANCE_NAMES = {
    "ekadashi": "Ekadashi",
    "purnima": "Purnima",
    "amavasya": "Amavasya",
    "pradosha": "Pradosh Vrat",
    "sankashti": "Sankashti Chaturthi",
    "pitru-paksha": "Pitru Paksha",
    "sankranti": "Sankranti",
    "pancaka": "Panchak",
}
SANKRANTI_NAMES = dict(
    zip(
        SIGN_IDS,
        (
            f"{s} Sankranti"
            for s in (
                "Mesh", "Vrishabh", "Mithun", "Kark", "Simha", "Kanya",
                "Tula", "Vrishchik", "Dhanu", "Makar", "Kumbh", "Meen",
            )
        ),
        strict=True,
    )
)  # fmt: skip
HORA_LORDS = ("sun", "moon", "mars", "mercury", "jupiter", "venus", "saturn")
PANCHANG_LABELS = {
    "sunrise": "Sunrise",
    "sunset": "Sunset",
    "moonrise": "Moonrise",
    "moonset": "Moonset",
    "tithi": "Tithi",
    "paksha": "Paksha",
    "nakshatra": "Nakshatra",
    "yoga": "Yoga",
    "karana": "Karana",
    "vara": "Weekday",
    "masa": "Month",
    "amanta": "Amanta month",
    "purnimanta": "Purnimanta month",
    "adhika": "Adhika",
    "choghadiya": "Choghadiya",
    "hora": "Hora",
    "day": "Day",
    "night": "Night",
}


def _tithi_names() -> dict:
    """The 30 tithis with their paksha: shukla_pratipada ... purnima, krishna_pratipada ...
    amavasya."""
    out = {}
    for n in range(1, 31):
        tid = _tithi_of(n)
        paksha = "shukla" if n <= 15 else "krishna"
        key = tid if tid in ("purnima", "amavasya") else f"{paksha}_{tid}"
        name = TITHI_DISPLAY[tid] if key == tid else f"{paksha.title()} {TITHI_DISPLAY[tid]}"
        out[key] = {"name": name, "tithi": tid, "paksha": paksha, "num": n}
    return out


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
            # Jyotih-prakasha in JN p. 142, v. 10; popular tables differ.
            "yoniGender": M.yoni_gender(i),
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
        "masas": {
            MASA_ID[m]: {"name": m, "num": i + 1, "adhikaName": f"Adhika {m}"}
            for i, m in enumerate(Mu.MASA)
        },
        "choghadiya": {
            name.lower(): {
                "name": name,
                "quality": {"Char": "neutral"}.get(
                    name, "good" if name in Mu.CHOGHADIYA_GOOD else "avoid"
                ),
                "note": CURRENT_PRACTICE,
            }
            for name in ("Amrit", "Shubh", "Labh", "Char", "Udveg", "Kaal", "Rog")
        },
        "windows": {
            k: {
                "name": n,
                "description": d,
                "source": WINDOW_SOURCES.get(k),
                "note": WINDOW_NOTES.get(k),
                "noteKey": WINDOW_NOTE_KEYS.get(k),
            }
            for k, (n, d) in WINDOWS.items()
        },
        "windowReasons": {k: {"name": v} for k, v in WINDOW_REASONS.items()},
        "windowNotes": WINDOW_SHARED_NOTES,
        "bhadraParts": BHADRA_PARTS,
        "bhadraResidences": {
            k: {"name": n, "description": d, "source": "Muhūrta-cintāmaṇi 1.45, p. 38"}
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
        "vivahLagnaRules": {
            k: {"name": n, "source": src, "level": lvl}
            for k, (n, src, lvl) in VIVAH_LAGNA_RULES.items()
        },
        "vivahLagnaGrades": VIVAH_LAGNA_GRADES,
        "vivahKuvarga": VIVAH_KUVARGA,
        "vivahPersonalRules": {
            k: {
                "name": n,
                "source": src,
                "level": lvl,
                "remedy": {"text": rem[0], "source": rem[1]} if rem else None,
            }
            for k, (n, src, lvl, rem) in VIVAH_PERSONAL_RULES.items()
        },
        "vivahJupiterBride": VIVAH_JUPITER_BRIDE,
        "vivahLifts": {k: {"name": n, "source": src} for k, (n, src) in VIVAH_LIFTS.items()},
        "vivahPersonalNotes": VIVAH_PERSONAL_NOTES,
        "grihaPraveshRules": {
            k: {"name": n, "source": src} for k, (n, src) in GRIHA_PRAVESH_RULES.items()
        },
        "grihaPraveshNotes": GRIHA_PRAVESH_NOTES,
        "mundanRules": {k: {"name": n, "source": src} for k, (n, src) in MUNDAN_RULES.items()},
        "mundanNotes": MUNDAN_NOTES,
        "annaprashanRules": {
            k: {"name": n, "source": src} for k, (n, src) in ANNAPRASHAN_RULES.items()
        },
        "annaprashanNotes": ANNAPRASHAN_NOTES,
        "akshararambhRules": {
            k: {"name": n, "source": src} for k, (n, src) in AKSHARARAMBH_RULES.items()
        },
        "akshararambhNotes": AKSHARARAMBH_NOTES,
        "sankrantiNotes": SANKRANTI_NOTES,
        "purchaseNotes": PURCHASE_NOTES,
        "horaSystems": HORA_SYSTEMS,
        "festivalRules": {
            group: {k: {"name": n, "source": src} for k, (n, src) in rules.items()}
            for group, rules in FESTIVAL_RULES.items()
        },
        "festivalNotes": FESTIVAL_NOTES,
        "festivalBasis": {
            "text": "Kept by the cited text's own rule",
            "popular_practice": "Popular practice; no text read gives the day",
        },
        "festivalCautions": FESTIVAL_CAUTIONS,
        "maghaMarks": {k: {"name": n, "source": src} for k, (n, src) in MAGHA_MARKS.items()},
        "maghaNotes": MAGHA_NOTES,
        "purnimaEarlierDateNote": PURNIMA_EARLIER_NOTE,
        "purnimaNames": {
            k: {"name": n, "note": note, "source": src}
            for k, (n, note, src) in PURNIMA_NAMES.items()
        },
        "gangaYogas": {k: {"name": v} for k, v in GANGA_YOGAS.items()},
        "amavasyaNames": {
            k: {"name": n, "note": note, "source": src, "popularName": AMAVASYA_POPULAR.get(k)}
            for k, (n, note, src) in AMAVASYA_NAMES.items()
        },
        # keyed by the rows' nameId: "<purnimanta month>_<paksha>", or "adhika_<paksha>"
        "ekadashiNames": {
            nid: {
                "name": name,
                "otherNames": list(others),
                "alsoPrinted": {"name": printed, "source": NS_P51} if printed else None,
                "popularName": popular,
                "source": f"Ekādaśī-māhātmya {folio}",
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
                    "text": "Phaladīpikā",
                    "verse": verse,
                    "edition": "Mantreśvara, translated by V. Subrahmanya Sastri, First edition, 1937",
                    "page": page,
                },
            }
            for k, (house, quote, verse, page) in SADE_SATI_PHASES.items()
        },
        "yogaChecks": {
            "kemadruma": {
                "name": "Some hold there is no Kemadruma when (Phaladīpikā 6.5, not applied):",
                "checks": {k: {"name": v} for k, v in YOGA_CHECKS.items()},
            }
        },
        "vargas": {
            f"D{d}": {
                "name": VARGA_NAMES[d],
                "signifies": VARGA_USES[d][0],
                "source": {**BPHS_1933, "verse": VARGA_USES[d][1]},
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
                "kind": "veto"
                if rid in VETOES
                else "support"
                if rid in SUPPORTS
                else "note"
                if rid in NOTES
                else "defect",
                "note": MUHURTA_RULE_NOTES.get(rid),
            }
            for rid in sorted({rid for _, rid in RULES} | {"favoured_hora", "malefic_hora"})
        },
        "ayanamsas": {k: {"name": v} for k, v in AYANAMSAS.items()},
        "eclipseRules": {k: {"name": n, "source": src} for k, (n, src) in ECLIPSE_RULES.items()},
        "eclipseNotes": ECLIPSE_NOTES,
        "pancakaBarred": {k: {"name": n, "source": src} for k, (n, src) in PANCAKA_BARRED.items()},
        "pancakaNames": {
            k: {"name": v, "basis": "popular_practice"} for k, v in PANCAKA_NAMES.items()
        },
        "pancakaNotes": PANCAKA_NOTES,
        "tithiNames": _tithi_names(),
        "festivals": {
            k: {
                "name": v,
                **({"popularName": FESTIVAL_POPULAR[k]} if k in FESTIVAL_POPULAR else {}),
            }
            for k, v in FESTIVAL_NAMES.items()
        },
        "festivalDays": {k: {"name": n, "kinds": ks} for k, (n, ks) in FESTIVAL_DAY_NAMES.items()},
        "observances": {k: {"name": v} for k, v in OBSERVANCE_NAMES.items()},
        "sankrantis": {k: {"name": v} for k, v in SANKRANTI_NAMES.items()},
        "horas": {g: {"name": f"{g.title()} hora"} for g in HORA_LORDS},
        "panchangLabels": {k: {"name": v} for k, v in PANCHANG_LABELS.items()},
        "kootas": {
            k: {"name": KOOTA_NAMES[k], "max": M.MAX[k], "source": M.SOURCES[k]} for k in M.MAX
        },
        "varnas": {k: {"name": v} for k, v in VARNAS.items()},
        "yonis": {y: {"name": y.capitalize()} for y in M.YONIS},
        "yoniGender": {
            "source": {
                "text": "Jyotirnibandha (quoting the Jyotiḥprakāśa)",
                "verse": "yoni 10–12",
                "edition": "Śivarāja, edited by Raṅganātha Śāstrī Vaidya, Ānandāśrama Sanskrit Series 85, Ānandāśrama Press, Poona, 1919 (Śaka 1841)",
                "page": "142",
            },
            "note": "Popular tables differ.",
        },
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
