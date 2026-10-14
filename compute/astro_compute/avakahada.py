"""A name's first syllable -> nakshatra pada, by the Avakahada chakra.

Source: docs/sources/avakahada.md.
  Table  the satapada-chakra verses quoted in Sitarama Jha, Ati-brhad
         Avakahada Cakram (1932), pp. 22-23, read with the vowels short as
         its Hindi gloss writes them; vowel length is ignored.
  Rules  Muhurta Martanda, Vivaha-prakarana v.55 and the author's commentary,
         p. 106:
         - the first letter of the name is looked up, and for a conjunct its
           first letter (Pradyumna gives pa);
         - ba = va, sha = sa and kha = ssa stand for each other when the
           name's syllable is missing from the chakra;
         - names do not begin with nga, nya or nna; read them as ga, ja, dda;
         - with several names, the later one ("pascadbhavam nama"). That is the
           name given later in life, not the last word of a full name, so the
           caller sends the name the person goes by and its first word is read.
  Lead decisions (14 Oct 2026): Abhijit's syllables count as Uttarashadha
  pada 4 (MC 6.52); a name still unmatched gets no nakshatra and a plain
  reason, never a guess.

Latin spellings hide distinctions the chakra makes (t/tta, d/dda, th/ttha,
sh/ssa), so a Latin name also returns the other readings that resolve to a
different pada. Devanagari is exact.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from .ids import NAKSHATRA_IDS

SOURCE = "MM vv. 54-55, pp. 104-106; Sitarama Jha 1932, pp. 22-23"
ABHIJIT = ("uttara_ashadha", 4)
RULES = {
    "conjunct_first_letter": "MM v.55, commentary p. 106",
    "equivalent_letters": "MM v.55, commentary p. 106",
    "nasal_read_as": "MM v.55, commentary p. 106",
    "abhijit_as_uttara_ashadha": "MC 6.52, p. 275",
}

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
        _nak, _pada = ABHIJIT if _star == "abhijit" else (_star, _i + 1)
        TABLE[tuple(_code.split("-"))] = Cell(_nak, _pada, _dv, _star == "abhijit")
assert len(TABLE) == 4 * len(_ROWS) == 112, "two chakra cells share a syllable"
assert all(star in NAKSHATRA_IDS or star == "abhijit" for star, _, _ in _ROWS)

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
    readings: list[tuple[str, str]] = field(default_factory=list)  # (consonant, vowel)
    conjunct: bool = False
    reason: str | None = None


def _deva(word: str) -> Parsed:
    p = Parsed(word, "devanagari")
    first = word[0]
    if first in _DEVA_VOWEL:
        p.readings.append(("", _DEVA_VOWEL[first]))
        return p
    if first not in _DEVA_CONSONANT:
        p.reason = f"'{first}' is not a letter in the Avakahada chakra."
        return p
    if word[1:2] == _NUKTA:
        p.reason = f"'{word[:2]}' has no letter in the Avakahada chakra."
        return p
    i = 1
    while word[i : i + 1] == _HALANT and word[i + 1 : i + 2] in _DEVA_CONSONANT:
        p.conjunct, i = True, i + 2
    sign = word[i : i + 1]
    if sign in _OTHER_SIGNS:
        p.reason = f"The Avakahada chakra has no syllable '{word[: i + 1]}'."
        return p
    p.readings.append((_DEVA_CONSONANT[first], _DEVA_SIGN.get(sign, "a")))
    return p


def _vowel(rest: str) -> str:
    return next((v for spelling, v in _LATIN_VOWEL if rest.startswith(spelling)), "a")


def _latin(word: str, letters: str) -> Parsed:
    p = Parsed(word, "latin")
    if letters[0] in _NO_LETTER:
        p.reason = f"'{_NO_LETTER[letters[0]]}' has no letter in the Avakahada chakra."
        return p
    if letters[0] not in _CONSONANT_LETTERS:
        p.readings.append(("", _vowel(letters)))
        return p
    if letters[0] == "c" and not letters.startswith("ch"):
        # An English c: s before e, i or y, otherwise k; both are offered.
        order = ("s", "k") if letters[1:2] in ("e", "i", "y") else ("k", "s")
        rest = letters[1:]
        while rest[:1] and rest[0] in _CONSONANT_LETTERS:
            p.conjunct, rest = True, rest[1:]
        vowel = _vowel(rest)
        p.readings += [(c, vowel) for c in order]
        return p
    for spelling, consonant, others in _LATIN_CONJUNCT:
        if letters.startswith(spelling):
            p.conjunct = True
            vowel = _vowel(letters[len(spelling) :])
            p.readings += [(c, vowel) for c in (consonant, *others)]
            return p
    for spelling, consonant, others in _LATIN_CONSONANT:
        if letters.startswith(spelling):
            rest = letters[len(spelling) :]
            while rest[:1] and rest[0] in _CONSONANT_LETTERS:
                p.conjunct, rest = True, rest[1:]
            vowel = _vowel(rest)
            p.readings += [(c, vowel) for c in (consonant, *others)]
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


def _resolve(consonant: str, vowel: str) -> tuple[Cell, str, list[str]] | None:
    """The chakra cell for a syllable, the syllable used, and the rules applied."""
    rules = []
    if consonant in READ_AS:
        consonant = READ_AS[consonant]
        rules.append("nasal_read_as")
    cell = TABLE.get((consonant, vowel))
    if cell is None and consonant in PAIR:
        consonant = PAIR[consonant]
        cell = TABLE.get((consonant, vowel))
        rules.append("equivalent_letters")
    if cell is None:
        return None
    if cell.abhijit:
        rules.append("abhijit_as_uttara_ashadha")
    return cell, iast(consonant, vowel), rules


def lookup(name: str) -> dict:
    """What the Avakahada chakra gives for a name. `matched` is False, with a
    plain `reason`, when the chakra has nothing for its first syllable."""
    p = _parse(name)
    out = {
        "nameUsed": p.word,
        "script": p.script,
        "exact": p.script == "devanagari",
        "source": SOURCE,
    }
    if p.reason:
        return {**out, "matched": False, "syllableRead": None, "reason": p.reason}
    hits = []
    for consonant, vowel in p.readings:
        hit = _resolve(consonant, vowel)
        if hit:
            hits.append((iast(consonant, vowel), *hit))
    if not hits:
        consonant, vowel = p.readings[0]
        reason = (
            f"The Avakahada chakra has no syllables with the vowel '{iast('', vowel)}'."
            if vowel in ("ai", "au", "ri")
            else f"The Avakahada chakra has no syllable '{iast(consonant, vowel)}'."
        )
        return {**out, "matched": False, "syllableRead": iast(consonant, vowel), "reason": reason}
    (read, cell, used, rules), *others = hits
    alternatives, seen = [], {(cell.nakshatra, cell.pada)}
    for _, alt, syllable, _ in others:
        if (alt.nakshatra, alt.pada) not in seen:
            seen.add((alt.nakshatra, alt.pada))
            alternatives.append(
                {
                    "syllable": syllable,
                    "devanagari": alt.devanagari,
                    "nakshatra": alt.nakshatra,
                    "pada": alt.pada,
                }
            )
    return {
        **out,
        "matched": True,
        "syllableRead": read,
        "syllable": used,
        "devanagari": cell.devanagari,
        "nakshatra": cell.nakshatra,
        "pada": cell.pada,
        "rules": (["conjunct_first_letter"] if p.conjunct else []) + rules,
        "alternatives": alternatives,
    }
