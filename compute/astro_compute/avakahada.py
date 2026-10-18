"""A name's first syllable -> nakshatra pada, by the Avakahada chakra.

Source: docs/sources/avakahada.md.
  Table  the satapada-chakra verses quoted in Sitarama Jha, Ati-brhad
         Avakahada Cakram (1932, "AC"), pp. 22-23.
  Rules  Muhurta Martanda (MM), Vivaha-prakarana v.55 and the author's
         commentary, p. 106, with AC pp. 24-26:
         - the first syllable of the name is looked up; for a conjunct, its
           first letter with the cluster's vowel (Pradyumna pa, Drupada du);
         - a and aa, i and ii, u and uu, e and ai, o and au count as one (AC p. 26);
         - ba = va, sha = sa and kha = ssa stand for each other when the
           name's syllable is missing (MM; AC p. 26);
         - names do not begin with nga, nya or nna; read them as ga, ja, dda;
         - r-vowel, which the chakra does not list, is read as ra (AC p. 25);
         - with several names, the one that came later in life
           ("pascad-bhava"), which is the name the person goes by now.
  Lead decisions (14 Oct 2026): Abhijit's syllables count as Uttarashadha
  pada 4 (MC 6.52). Our readings, labelled as such in every response:
  r-vowel after a consonant becomes ra and the conjunct rule applies (kr gives
  ka); a consonant the chakra lists only once takes that cell whatever its
  vowel (Dhruv gives dha). Anything still unmatched gets no nakshatra and a
  plain reason, never a guess.

Latin spellings hide distinctions the chakra makes (t/tta, d/dda, th/ttha,
sh/ssa, kr/kri), so a Latin name also returns the other readings that land in a
different pada. Only Devanagari read by the cited rules alone is exact.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from .ids import NAKSHATRA_IDS

SOURCE = "MM vv. 54–55, pp. 104–106; Sītārāma Jhā 1932 pp. 22–26"
ABHIJIT = ("uttara_ashadha", 4)
RULES = {
    "conjunct_first_letter": "MM v.55, commentary p. 106",
    "vowel_pairs": "Sītārāma Jhā 1932 p. 26",
    "equivalent_letters": "MM v.55, commentary p. 106; Sītārāma Jhā 1932 p. 26",
    "nasal_read_as": "MM v.55, commentary p. 106",
    "r_vowel_as_ra": "Sītārāma Jhā 1932 p. 25",
    "abhijit_as_uttara_ashadha": "MC 6.52, p. 275",
    "r_in_syllable_as_ra": "our reading of Sītārāma Jhā 1932 p. 25 with MM v.55",
    "single_cell_consonant": "our reading; no text read states it",
}
OUR_READINGS = {"r_in_syllable_as_ra", "single_cell_consonant"}

# Consonants are internal ASCII codes: tt tth dd ddh nn are the retroflex row,
# sh is the palatal sibilant, ss the retroflex one, ng and ny the nasals.
_ROWS = [
    ("ashwini", "c-u c-e c-o l-a", "चू चे चो ला"),
    ("bharani", "l-i l-u l-e l-o", "ली लू ले लो"),
    ("krittika", "-a -i -u -e", "अ ई ऊ ए"),
    ("rohini", "-o v-a v-i v-u", "ओ वा वी वू"),
    ("mrigashira", "v-e v-o k-a k-i", "वे वो का की"),
    ("ardra", "k-u gh-a ng-a ch-a", "कू घ ङ छा"),
    ("punarvasu", "k-e k-o h-a h-i", "के को हा ही"),
    ("pushya", "h-u h-e h-o dd-a", "हू हे हो डा"),
    ("ashlesha", "dd-i dd-u dd-e dd-o", "डी डू डे डो"),
    ("magha", "m-a m-i m-u m-e", "मा मी मू मे"),
    ("purva_phalguni", "m-o tt-a tt-i tt-u", "मो टा टी टू"),
    ("uttara_phalguni", "tt-e tt-o p-a p-i", "टे टो पा पी"),
    ("hasta", "p-u ss-a nn-a tth-a", "पू ष णा ठा"),
    ("chitra", "p-e p-o r-a r-i", "पे पो रा री"),
    ("swati", "r-u r-e r-o t-a", "रू रे रो ता"),
    ("vishakha", "t-i t-u t-e t-o", "ती तू ते तो"),
    ("anuradha", "n-a n-i n-u n-e", "ना नी नू ने"),
    ("jyeshtha", "n-o y-a y-i y-u", "नो या यी यू"),
    ("mula", "y-e y-o bh-a bh-i", "ये यो भा भी"),
    ("purva_ashadha", "bh-u dh-a ph-a ddh-a", "भू धा फा ढा"),
    ("uttara_ashadha", "bh-e bh-o j-a j-i", "भे भो जा जी"),
    ("abhijit", "j-u j-e j-o kh-a", "जू जे जो खा"),
    ("shravana", "kh-i kh-u kh-e kh-o", "खी खू खे खो"),
    ("dhanishta", "g-a g-i g-u g-e", "गा गी गू गे"),
    ("shatabhisha", "g-o s-a s-i s-u", "गो सा सी सू"),
    ("purva_bhadrapada", "s-e s-o d-a d-i", "से सो दा दी"),
    ("uttara_bhadrapada", "d-u th-a jh-a ny-a", "दू थ झ ञ"),
    ("revati", "d-e d-o c-a c-i", "दे दो चा ची"),
]
_IAST = {
    "tt": "ṭ", "tth": "ṭh", "dd": "ḍ", "ddh": "ḍh", "nn": "ṇ", "ss": "ṣ", "sh": "ś", "ng": "ṅ",
    "ny": "ñ",
}  # fmt: skip


def iast(consonant: str, vowel: str) -> str:
    return _IAST.get(consonant, consonant) + {"ri": "ṛ"}.get(vowel, vowel)


@dataclass(frozen=True)
class Cell:
    nakshatra: str
    pada: int
    syllable: str  # IAST
    devanagari: str
    abhijit: bool


TABLE: dict[tuple[str, str], Cell] = {}
CHAKRA: list[dict] = []  # the chakra as printed, for meta
for _star, _codes, _deva in _ROWS:
    _cells = list(zip(_codes.split(), _deva.split(), strict=True))
    CHAKRA.append(
        {
            "star": _star,
            "padas": [
                {"pada": i + 1, "syllable": iast(*code.split("-")), "devanagari": dv}
                for i, (code, dv) in enumerate(_cells)
            ],
        }
    )
    for _i, (_code, _dv) in enumerate(_cells):
        _key = tuple(_code.split("-"))
        _nak, _pada = ABHIJIT if _star == "abhijit" else (_star, _i + 1)
        TABLE[_key] = Cell(_nak, _pada, iast(*_key), _dv, _star == "abhijit")
assert len(TABLE) == 4 * len(_ROWS) == 112, "two chakra cells share a syllable"
assert all(star in NAKSHATRA_IDS or star == "abhijit" for star, _, _ in _ROWS)

_BY_CONSONANT: dict[str, list[Cell]] = defaultdict(list)
for (_c, _v), _cell in TABLE.items():
    _BY_CONSONANT[_c].append(_cell)
SINGLE = {c: cells[0] for c, cells in _BY_CONSONANT.items() if c and len(cells) == 1}

VOWEL_PAIR = {"ai": "e", "au": "o"}
READ_AS = {"ng": "g", "ny": "j", "nn": "dd"}
PAIR = {"b": "v", "v": "b", "sh": "s", "s": "sh", "kh": "ss", "ss": "kh"}

# --- Devanagari -------------------------------------------------------------------
_DEVA_CONSONANT = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng", "च": "c", "छ": "ch", "ज": "j",
    "झ": "jh", "ञ": "ny", "ट": "tt", "ठ": "tth", "ड": "dd", "ढ": "ddh", "ण": "nn", "त": "t",
    "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p", "फ": "ph", "ब": "b", "भ": "bh",
    "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "ss", "स": "s", "ह": "h",
}  # fmt: skip
_DEVA_VOWEL = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai",
    "ओ": "o", "औ": "au", "ऋ": "ri", "ॠ": "ri",
}  # fmt: skip
_DEVA_SIGN = {
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o",
    "ौ": "au", "ृ": "ri", "ॄ": "ri",
}  # fmt: skip
_HALANT, _NUKTA = "्", "़"
_OTHER_SIGNS = set("ॅॆॉॊॢॣ")  # candra and short e/o, vocalic l: not in the chakra

# --- Latin --------------------------------------------------------------------------
# (spelling, consonant, other consonants the same spelling can stand for)
_LATIN_CONSONANT = [
    ("chh", "ch", ()), ("ch", "c", ("ch",)), ("kh", "kh", ()), ("gh", "gh", ()),
    ("jh", "jh", ()), ("th", "th", ("tth", "t")), ("dh", "dh", ("ddh",)), ("ph", "ph", ()),
    ("bh", "bh", ()), ("sh", "sh", ("ss",)), ("k", "k", ()), ("g", "g", ()), ("j", "j", ()),
    ("t", "t", ("tt",)), ("d", "d", ("dd",)), ("n", "n", ()), ("p", "p", ()), ("b", "b", ()),
    ("m", "m", ()), ("y", "y", ()), ("r", "r", ()), ("l", "l", ()), ("v", "v", ()),
    ("w", "v", ()), ("s", "s", ()), ("h", "h", ()),
]  # fmt: skip
# Conjuncts whose first letter differs from the first Latin letter: ksh is क्ष,
# and gy, gn, jn are the usual spellings of ज्ञ (or a plain g + y/n cluster).
_LATIN_CONJUNCT = [
    ("ksh", "k", ()), ("gny", "j", ("g",)), ("gy", "j", ("g",)), ("gn", "j", ("g",)),
    ("jn", "j", ()),
]  # fmt: skip
_NO_LETTER = {"f": "fa", "z": "za", "q": "qa", "x": "xa"}
_LATIN_VOWEL = [
    ("aa", "a"), ("ai", "ai"), ("au", "au"), ("ou", "au"), ("ee", "i"), ("ii", "i"),
    ("oo", "u"), ("uu", "u"), ("a", "a"), ("i", "i"), ("u", "u"), ("e", "e"), ("o", "o"),
]  # fmt: skip
_CONSONANT_LETTERS = set("bcdfghjklmnpqrstvwxyz")


@dataclass
class Parsed:
    word: str
    script: str
    readings: list[tuple[str, str, bool]] = field(
        default_factory=list
    )  # consonant, vowel, conjunct
    reason: str | None = None


def _deva(word: str) -> Parsed:
    p = Parsed(word, "devanagari")
    first = word[0]
    if first in _DEVA_VOWEL:
        p.readings.append(("", _DEVA_VOWEL[first], False))
        return p
    if first not in _DEVA_CONSONANT:
        p.reason = f"'{first}' is not a letter in the Avakahaḍā chakra."
        return p
    if word[1:2] == _NUKTA:
        p.reason = f"'{word[:2]}' has no letter in the Avakahaḍā chakra."
        return p
    i, conjunct = 1, False
    while word[i : i + 1] == _HALANT and word[i + 1 : i + 2] in _DEVA_CONSONANT:
        conjunct, i = True, i + 2
    sign = word[i : i + 1]
    if sign in _OTHER_SIGNS:
        p.reason = f"The Avakahaḍā chakra has no syllable '{word[: i + 1]}'."
        return p
    p.readings.append((_DEVA_CONSONANT[first], _DEVA_SIGN.get(sign, "a"), conjunct))
    return p


def _vowel(rest: str) -> str:
    return next((v for spelling, v in _LATIN_VOWEL if rest.startswith(spelling)), "a")


def _cluster(rest: str) -> tuple[str, bool]:
    """Skip the rest of a consonant cluster: (what follows it, whether there was one)."""
    conjunct = False
    while rest[:1] and rest[0] in _CONSONANT_LETTERS:
        conjunct, rest = True, rest[1:]
    return rest, conjunct


def _latin(word: str, letters: str) -> Parsed:
    p = Parsed(word, "latin")
    if letters[0] in _NO_LETTER:
        p.reason = f"'{_NO_LETTER[letters[0]]}' has no letter in the Avakahaḍā chakra."
        return p
    if letters[0] not in _CONSONANT_LETTERS:
        p.readings.append(("", _vowel(letters), False))
        return p
    if letters[0] == "c" and not letters.startswith("ch"):
        # An English c: s before e, i or y, otherwise k; both are offered.
        order = ("s", "k") if letters[1:2] in ("e", "i", "y") else ("k", "s")
        rest, conjunct = _cluster(letters[1:])
        p.readings += [(c, _vowel(rest), conjunct) for c in order]
        return p
    for spelling, consonant, others in _LATIN_CONJUNCT:
        if letters.startswith(spelling):
            vowel = _vowel(letters[len(spelling) :])
            p.readings += [(c, vowel, True) for c in (consonant, *others)]
            return p
    for spelling, consonant, others in _LATIN_CONSONANT:
        if letters.startswith(spelling):
            rest, conjunct = _cluster(letters[len(spelling) :])
            p.readings += [(c, _vowel(rest), conjunct) for c in (consonant, *others)]
            return p
    p.reason = f"'{word}' cannot be read."
    return p


def _parse(name: str) -> Parsed:
    words = name.split()
    word = unicodedata.normalize("NFC", words[0]) if words else ""
    if not word:
        return Parsed("", "other", reason="No name was given.")
    if "ऀ" <= word[0] <= "ॿ":
        return _deva(word)
    folded = unicodedata.normalize("NFKD", word.lower())
    first = next((c for c in folded if c.isalpha()), "")
    letters = "".join(c for c in folded if c.isascii() and c.isalpha())
    if first.isascii() and letters:
        return _latin(word, letters)
    return Parsed(word, "other", reason="Only names in Latin or Devanagari letters can be read.")


def _resolve(consonant: str, vowel: str, conjunct: bool) -> tuple[Cell, list[str]] | None:
    """The chakra cell for a syllable and the rules applied to reach it."""
    rules = ["conjunct_first_letter"] if conjunct else []
    if vowel in VOWEL_PAIR:
        vowel = VOWEL_PAIR[vowel]
        rules.append("vowel_pairs")
    if vowel == "ri":
        if consonant:  # कृ read as क्र, then the conjunct's first letter: ka
            rules += ["r_in_syllable_as_ra", "conjunct_first_letter"]
        else:
            consonant = "r"
            rules.append("r_vowel_as_ra")
        vowel = "a"
    if consonant in READ_AS:
        consonant = READ_AS[consonant]
        rules.append("nasal_read_as")
    cell = TABLE.get((consonant, vowel))
    if cell is None and (consonant in PAIR and (PAIR[consonant], vowel) in TABLE):
        cell = TABLE[(PAIR[consonant], vowel)]
        rules.append("equivalent_letters")
    if cell is None and consonant in SINGLE:
        cell = SINGLE[consonant]
        rules.append("single_cell_consonant")
    if cell is None:
        return None
    if cell.abhijit:
        rules.append("abhijit_as_uttara_ashadha")
    return cell, list(dict.fromkeys(rules))


def lookup(name: str) -> dict:
    """What the Avakahada chakra gives for a name. `matched` is False, with a
    plain `reason`, when the chakra has nothing for its first syllable."""
    p = _parse(name)
    out = {"nameUsed": p.word, "script": p.script, "source": SOURCE}
    if p.reason:
        return {**out, "matched": False, "exact": False, "syllableRead": None, "reason": p.reason}
    hits = []
    for order, (consonant, vowel, conjunct) in enumerate(p.readings):
        hit = _resolve(consonant, vowel, conjunct)
        if hit:
            cell, rules = hit
            ours = bool(OUR_READINGS & set(rules))
            hits.append((ours, order, iast(consonant, vowel), cell, rules))
    if not hits:
        consonant, vowel, _ = p.readings[0]
        read = iast(consonant, vowel)
        return {
            **out,
            "matched": False,
            "exact": False,
            "syllableRead": read,
            "reason": f"The Avakahaḍā chakra has no syllable '{read}'.",
        }
    # Readings the cited rules reach come before our readings, then spelling order.
    hits.sort(key=lambda h: (h[0], h[1]))
    (ours, _, read, cell, rules), *others = hits
    alternatives, seen = [], {(cell.nakshatra, cell.pada)}
    for alt_ours, _, _, alt, _ in others:
        if (alt.nakshatra, alt.pada) not in seen:
            seen.add((alt.nakshatra, alt.pada))
            alternatives.append(
                {
                    "syllable": alt.syllable,
                    "devanagari": alt.devanagari,
                    "nakshatra": alt.nakshatra,
                    "pada": alt.pada,
                    "ourReading": alt_ours,
                }
            )
    return {
        **out,
        "matched": True,
        "exact": p.script == "devanagari" and not ours,
        "ourReading": ours,
        "syllableRead": read,
        "syllable": cell.syllable,
        "devanagari": cell.devanagari,
        "nakshatra": cell.nakshatra,
        "pada": cell.pada,
        "rules": rules,
        "alternatives": alternatives,
    }
