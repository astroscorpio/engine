"""POST /v1/matching: Ashtakoota (guna milan) for a bride and a groom.

Every table below is transcribed from docs/sources/ashtakoota.md, which quotes
the scanned verse for each. Citations use that file's keys:

  MC   Muhurta Chintamani ch. 6 with the Piyushadhara commentary
  MC49 the 1949 Khemraj edition of MC, with printed point tables
  MM   Muhurta Martanda (1909 edition)
  BJS  Brihat Jyotishsara (1892)
  DM   Daivajna-manohara, quoted inside MC

Decisions taken by the lead where the sources leave a choice are marked
"Decision". Mangal (kuja) dosha comes from kuja.py, the rule the chart page
uses too, so the two pages cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from jyotisha.chart import SIGN_LORDS, Chart
from jyotisha.muhurta import TARA_NAMES
from jyotisha.vargas import varga

from . import kuja as K
from .chart_service import cast, moon_uncertainty
from .errors import invalid
from .fmt import provenance
from .ids import GRAHA_ID, NAKSHATRA_IDS, SIGN_IDS, slug
from .models import ChartIn, MatchingRequest, NakshatraIn

# --- varna: MC 6.22, p. 245; BJS vv. 576-578; MM v.10 ------------------------
# By Moon sign. One point when the groom's varna is equal to or higher than the bride's.
VARNA_OF_SIGN = {
    3: "brahmana", 7: "brahmana", 11: "brahmana",
    0: "kshatriya", 4: "kshatriya", 8: "kshatriya",
    1: "vaishya", 5: "vaishya", 9: "vaishya",
    2: "shudra", 6: "shudra", 10: "shudra",
}  # fmt: skip
VARNA_RANK = {"brahmana": 4, "kshatriya": 3, "vaishya": 2, "shudra": 1}

# --- vashya: groups BJS vv. 579-582, p. 183; points table BJS p. 187 ----------
# Decision (lead): our reading of BJS. Leo is vanachara, Cancer and Scorpio keeta,
# Sagittarius and Capricorn split at 15 degrees; the one asymmetric cell
# (jalachara/keeta) takes the lower value. The UI labels this as our reading.
VASHYA_GROUPS = ["chatushpada", "manava", "jalachara", "vanachara", "keeta"]
VASHYA_POINTS = [
    [2, 0.5, 1, 0, 1],
    [0.5, 2, 0, 0, 0],
    [1, 0, 2, 2, 0],
    [0, 0, 2, 2, 0],
    [1, 0, 0, 0, 2],
]


def vashya_group(sign: int, deg: float) -> str:
    if sign in (0, 1):
        return "chatushpada"
    if sign in (2, 5, 6):
        return "manava"
    if sign in (3, 7):
        return "keeta"
    if sign == 4:
        return "vanachara"
    if sign == 8:
        return "manava" if deg < 15 else "chatushpada"
    if sign == 9:
        return "chatushpada" if deg < 15 else "jalachara"
    return "jalachara"


# --- tara: MC 6.24, p. 246; points DM in MC p. 246 ----------------------------
# Count inclusively both ways, remainder mod 9 (0 read as 9); 3, 5 and 7 are
# inauspicious. Auspicious both ways 3, one way 1.5, neither 0.
TARA_BAD = {3, 5, 7}
TARA_PURE = {2, 4, 6, 8, 9}  # "pure both ways", the bhakoot cancellation (Rajamartanda, MC p. 255)

# --- yoni: MC 6.25-26, p. 247 (assignment); MC49 p. 84 (printed table) --------
YONIS = [
    "horse", "elephant", "sheep", "serpent", "dog", "cat", "rat",
    "cow", "buffalo", "tiger", "deer", "monkey", "mongoose", "lion",
]  # fmt: skip
YONI_OF_NAKSHATRA = [
    "horse", "elephant", "sheep", "serpent", "serpent", "dog", "cat",  # Ashwini..Punarvasu
    "sheep", "cat", "rat", "rat", "cow", "buffalo", "tiger",  # Pushya..Chitra
    "buffalo", "tiger", "deer", "deer", "dog", "monkey", "mongoose",  # Swati..U.Ashadha
    "monkey", "lion", "horse", "lion", "cow", "elephant",  # Shravana..Revati
]  # fmt: skip
# MC49 p. 84 (PDF 195), majority of four reads, rows and columns in YONIS order.
# None is the cell damaged in print (cow row, buffalo column).
YONI_PRINTED = [
    [4, 2, 2, 3, 2, 2, 2, 1, 0, 1, 3, 3, 2, 1],
    [2, 4, 3, 3, 2, 2, 2, 2, 3, 1, 2, 2, 2, 0],
    [2, 3, 4, 2, 1, 2, 1, 3, 3, 1, 2, 0, 3, 1],
    [3, 3, 2, 4, 2, 1, 1, 1, 1, 2, 2, 2, 0, 2],
    [2, 2, 1, 2, 4, 2, 1, 2, 2, 1, 0, 2, 1, 1],
    [2, 2, 2, 3, 2, 4, 0, 2, 2, 2, 3, 3, 2, 2],
    [2, 2, 1, 1, 1, 0, 4, 2, 2, 2, 2, 2, 2, 1],
    [1, 2, 3, 2, 3, 2, 2, 4, None, 0, 3, 2, 2, 1],
    [0, 2, 3, 2, 2, 2, 2, 3, 4, 1, 2, 3, 2, 2],
    [1, 2, 1, 1, 1, 1, 2, 1, 1, 4, 1, 1, 2, 2],
    [3, 3, 2, 2, 0, 3, 2, 3, 2, 1, 4, 2, 2, 2],
    [3, 3, 0, 2, 2, 3, 2, 2, 2, 1, 2, 4, 3, 2],
    [2, 3, 3, 0, 1, 2, 1, 2, 2, 2, 2, 3, 4, 2],
    [1, 0, 1, 2, 1, 1, 0, 0, 3, 2, 1, 2, 2, 4],
]
# Decision (lead, 14 Oct 2026): no source gives a direction for yoni, so each
# asymmetric pair takes the lower printed value, except cow/buffalo = 3 (the
# legible buffalo row, and MM's commentary calls them friends).
COW_BUFFALO = 3


def _yoni_points(a: str, b: str) -> int:
    i, j = YONIS.index(a), YONIS.index(b)
    if {a, b} == {"cow", "buffalo"}:
        return COW_BUFFALO
    return min(YONI_PRINTED[i][j], YONI_PRINTED[j][i])


# --- graha maitri: MC 6.27-28, p. 248 (natural relations); points DM in MC p. 249
FRIENDS = {
    "Sun": ({"Moon", "Mars", "Jupiter"}, {"Mercury"}),
    "Moon": ({"Sun", "Mercury"}, {"Mars", "Jupiter", "Venus", "Saturn"}),
    "Mars": ({"Sun", "Moon", "Jupiter"}, {"Venus", "Saturn"}),
    "Mercury": ({"Sun", "Venus"}, {"Mars", "Jupiter", "Saturn"}),
    "Jupiter": ({"Sun", "Moon", "Mars"}, {"Saturn"}),
    "Venus": ({"Mercury", "Saturn"}, {"Mars", "Jupiter"}),
    "Saturn": ({"Mercury", "Venus"}, {"Jupiter"}),
}  # (friends, neutrals); everyone else is an enemy
MAITRI_POINTS = {
    ("friend", "friend"): 5,
    ("friend", "neutral"): 4,
    ("neutral", "neutral"): 3,
    ("friend", "enemy"): 1,
    ("neutral", "enemy"): 0.5,
    ("enemy", "enemy"): 0,
}


def relation(a: str, b: str) -> str:
    friends, neutrals = FRIENDS[a]
    return "friend" if b in friends else "neutral" if b in neutrals else "enemy"


def maitri_points(a: str, b: str) -> float:
    if a == b:
        return 5
    pair = tuple(sorted((relation(a, b), relation(b, a)), key=["friend", "neutral", "enemy"].index))
    return MAITRI_POINTS[pair]


def mutual_friends(a: str, b: str) -> bool:
    return a == b or (relation(a, b) == "friend" and relation(b, a) == "friend")


# --- gana: MC 6.29, p. 249 (assignment); points DM in MC p. 250 --------------
GANA_OF_NAKSHATRA = [
    "deva", "manushya", "rakshasa", "manushya", "deva", "manushya", "deva",  # Ashwini..Punarvasu
    "deva", "rakshasa", "rakshasa", "manushya", "manushya", "deva", "rakshasa",  # Pushya..Chitra
    "deva", "rakshasa", "deva", "rakshasa", "rakshasa", "manushya", "manushya",  # Swati..U.Ashadha
    "deva", "rakshasa", "rakshasa", "manushya", "manushya", "deva",  # Shravana..Revati
]  # fmt: skip
# Decision (lead): the commentary's direction-aware scheme, groom x bride.
# BJS p. 189 prints a different, symmetric-leaning table (kept as a variant in the sources file).
GANA_POINTS = {
    ("deva", "deva"): 6, ("deva", "manushya"): 5, ("deva", "rakshasa"): 0,
    ("manushya", "deva"): 4, ("manushya", "manushya"): 6, ("manushya", "rakshasa"): 0,
    ("rakshasa", "deva"): 2, ("rakshasa", "manushya"): 1, ("rakshasa", "rakshasa"): 6,
}  # fmt: skip  # (groom, bride)

# --- bhakoot: MC 6.31, p. 251; cancellations MC 6.32-33 and p. 256 -----------
BHAKOOT_BAD = {frozenset((6, 8)): "6/8", frozenset((5, 9)): "5/9", frozenset((2, 12)): "2/12"}

# --- nadi: MC 6.34, p. 257; MC49 p. 84 (same 0, different 8) -----------------
NADI_OF_NAKSHATRA = [
    "adi", "madhya", "antya", "antya", "madhya", "adi", "adi",  # Ashwini..Punarvasu
    "madhya", "antya", "antya", "madhya", "adi", "adi", "madhya",  # Pushya..Chitra
    "antya", "antya", "madhya", "adi", "adi", "madhya", "antya",  # Swati..U.Ashadha
    "antya", "madhya", "adi", "adi", "madhya", "antya",  # Shravana..Revati
]  # fmt: skip

SOURCES = {
    "varna": "MC 6.22, p. 245",
    "vashya": "BJS vv. 579-582, p. 183; table p. 187 (our reading)",
    "tara": "MC 6.24, p. 246",
    "yoni": "MC 6.25-26, p. 247; MC49 p. 84",
    "graha_maitri": "MC 6.27-28, p. 248; DM in MC p. 249",
    "gana": "MC 6.29-30, p. 249; DM in MC p. 250",
    "bhakoot": "MC 6.31-33, pp. 251-257",
    "nadi": "MC 6.34 and 6.36, pp. 257-261",
}
MAX = {
    "varna": 1,
    "vashya": 2,
    "tara": 3,
    "yoni": 4,
    "graha_maitri": 5,
    "gana": 6,
    "bhakoot": 7,
    "nadi": 8,
}
PENDING: list[str] = []
AUSPICIOUS_ABOVE = 18  # MM v.1, p. 41: more than eighteen is auspicious


@dataclass(frozen=True)
class Moon:
    name: str | None
    nakshatra: int  # 0..26
    pada: int  # 1..4
    sign: int  # 0..11
    navamsha: int  # 0..11
    basis: str
    uncertain: bool
    # The Moon's degree in its sign: exact for a chart, a pada's span otherwise.
    deg_range: tuple[float, float]
    chart: Chart | None = None  # None for a partner known only by birth star
    time_known: bool = False

    @property
    def lord(self) -> str:
        return SIGN_LORDS[self.sign]

    @property
    def navamsha_lord(self) -> str:
        return SIGN_LORDS[self.navamsha]

    def row(self) -> dict:
        return {
            "name": self.name,
            "moonSign": SIGN_IDS[self.sign],
            "nakshatra": NAKSHATRA_IDS[self.nakshatra],
            "pada": self.pada,
            "navamshaSign": SIGN_IDS[self.navamsha],
            "basis": self.basis,
            "moonUncertain": self.uncertain,
        }


def moon_of(partner: ChartIn | NakshatraIn) -> Moon:
    if isinstance(partner, NakshatraIn):
        if partner.nakshatra not in NAKSHATRA_IDS:
            raise invalid(f"unknown nakshatra {partner.nakshatra!r}", "nakshatra")
        n = NAKSHATRA_IDS.index(partner.nakshatra)
        quarter = n * 4 + partner.pada - 1  # 108 padas; nine to a sign, and each is one navamsha
        start = (quarter % 9) * 10 / 3  # degrees into the sign where this pada begins
        return Moon(
            partner.name, n, partner.pada, quarter // 9, quarter % 12, "nakshatra", False,
            (start, start + 10 / 3),
        )  # fmt: skip
    chart, birth = cast(partner)
    moon = chart.grahas["Moon"]
    uncertain = partner.timeUnknown and any(moon_uncertainty(partner, birth))
    navamsha = int(varga(moon.longitude, 9) // 30)
    deg = moon.degree
    return Moon(
        partner.name, moon.nakshatra, moon.pada, moon.sign, navamsha, "chart", uncertain,
        (deg, deg), chart, not partner.timeUnknown,
    )  # fmt: skip


def _tara(from_n: int, to_n: int) -> int:
    """Remainder 1..9 of the inclusive count from one star to the other."""
    return ((to_n - from_n) % 27 + 1) % 9 or 9


def koota(kid: str, points, bride=None, groom=None, **extra) -> dict:
    row = {
        "id": kid,
        "points": points,
        "max": MAX[kid],
        "pending": points is None,
        "bride": bride,
        "groom": groom,
        "detail": None,
        "dosha": False,
        "cancelled": False,
        "note": None,
        "source": SOURCES[kid],
    }
    row.update(extra)
    return row


def build(req: MatchingRequest) -> dict:
    b, g = moon_of(req.bride), moon_of(req.groom)
    notes: list[str] = []

    same_star = b.nakshatra == g.nakshatra
    same_sign = b.sign == g.sign
    # MC 6.36, p. 261: these cases carry no nadi or gana dosha.
    if same_sign and not same_star:
        exception = "same_sign_different_nakshatra"
    elif same_star and not same_sign:
        exception = "same_nakshatra_different_sign"
    elif same_star and b.pada != g.pada:
        exception = "same_nakshatra_different_pada"
    else:
        exception = None
    if same_star and same_sign and b.pada == g.pada:
        notes.append("same_nakshatra_same_pada")  # fatal per Narada; MM v.6

    # varna
    vb, vg = VARNA_OF_SIGN[b.sign], VARNA_OF_SIGN[g.sign]
    varna = koota("varna", 1 if VARNA_RANK[vg] >= VARNA_RANK[vb] else 0, vb, vg)

    # vashya: a pada straddling 15 degrees of Sagittarius or Capricorn leaves the
    # group open when only the birth star is known.
    groups = []
    for m in (b, g):
        lo, hi = (vashya_group(m.sign, d) for d in (m.deg_range[0], m.deg_range[1] - 1e-9))
        groups.append(lo if lo == hi else None)
    if None in groups:
        vashya = koota("vashya", None, *groups, note="vashya_group_uncertain")
    else:
        vb_, vg_ = groups
        points = VASHYA_POINTS[VASHYA_GROUPS.index(vb_)][VASHYA_GROUPS.index(vg_)]
        vashya = koota("vashya", points, vb_, vg_, note="our_reading_of_bjs")

    # tara
    t_bg, t_gb = _tara(b.nakshatra, g.nakshatra), _tara(g.nakshatra, b.nakshatra)
    good = (t_bg not in TARA_BAD) + (t_gb not in TARA_BAD)
    tara = koota(
        "tara",
        {2: 3, 1: 1.5, 0: 0}[good],
        slug(TARA_NAMES[t_bg - 1]),
        slug(TARA_NAMES[t_gb - 1]),
    )
    if exception == "same_sign_different_nakshatra" and good < 2:
        tara["note"] = "tara_clear_same_sign"  # MC 6.36 commentary
        notes.append("tara_clear_same_sign")

    # yoni
    yb, yg = YONI_OF_NAKSHATRA[b.nakshatra], YONI_OF_NAKSHATRA[g.nakshatra]
    yoni = koota("yoni", _yoni_points(yb, yg), yb, yg)

    # graha maitri
    maitri_pts = maitri_points(b.lord, g.lord)
    maitri = koota("graha_maitri", maitri_pts, GRAHA_ID[b.lord], GRAHA_ID[g.lord])
    lords_friendly = mutual_friends(b.lord, g.lord)
    navamsha_friendly = mutual_friends(b.navamsha_lord, g.navamsha_lord)

    # gana (groom x bride)
    gb, gg = GANA_OF_NAKSHATRA[b.nakshatra], GANA_OF_NAKSHATRA[g.nakshatra]
    gana_pts = GANA_POINTS[(gg, gb)]
    gana = koota("gana", gana_pts, gb, gg, dosha=gana_pts == 0)
    if gana["dosha"]:
        if exception:
            gana.update(cancelled=True, note=exception)
        elif lords_friendly or navamsha_friendly:  # MC 6.33, p. 257
            gana.update(
                cancelled=True,
                note="sign_lords_friendly" if lords_friendly else "navamsha_lords_friendly",
            )

    # nadi
    nb, ng = NADI_OF_NAKSHATRA[b.nakshatra], NADI_OF_NAKSHATRA[g.nakshatra]
    nadi = koota("nadi", 0 if nb == ng else 8, nb, ng, dosha=nb == ng)
    if nadi["dosha"] and exception:
        nadi.update(cancelled=True, note=exception)
    nadi_clear = not nadi["dosha"] or nadi["cancelled"]

    # bhakoot: count the groom's Moon sign from the bride's, and back
    d = (g.sign - b.sign) % 12 + 1
    back = (b.sign - g.sign) % 12 + 1
    bad = BHAKOOT_BAD.get(frozenset((d, back)))
    detail = bad or {1: "1/1", 7: "1/7"}.get(d) or f"{min(d, back)}/{max(d, back)}"
    bhakoot = koota(
        "bhakoot",
        0 if bad else 7,
        SIGN_IDS[b.sign],
        SIGN_IDS[g.sign],
        detail=detail,
        dosha=bool(bad),
    )
    if bad:
        # MC p. 256: any one condition lifts it, and every one needs nadi clear.
        reason = None
        if b.lord == g.lord:
            reason = "same_sign_lord"
        elif lords_friendly:
            reason = "sign_lords_friendly"
        elif t_bg in TARA_PURE and t_gb in TARA_PURE:
            reason = "tara_pure_both_ways"
        if reason and nadi_clear:
            bhakoot.update(cancelled=True, note=reason)
        elif reason:
            bhakoot["note"] = f"{reason}_but_nadi_dosha"
        elif navamsha_friendly:
            # Condition 3 also needs the navamsha lords to be strong, which is not assessed.
            bhakoot["note"] = "navamsha_lords_friendly_strength_not_assessed"

    kootas = [varna, vashya, tara, yoni, maitri, gana, bhakoot, nadi]
    total = sum(k["points"] for k in kootas if k["points"] is not None)
    max_points = sum(k["max"] for k in kootas if k["points"] is not None)
    open_points = sum(k["max"] for k in kootas if k["points"] is None)
    if total > AUSPICIOUS_ABOVE:
        auspicious = True
    elif total + open_points > AUSPICIOUS_ABOVE:
        auspicious = None  # the pending kootas could still carry it over 18
    else:
        auspicious = False
    if b.uncertain or g.uncertain:
        notes.append("moon_uncertain_birth_time_unknown")

    return {
        "bride": b.row(),
        "groom": g.row(),
        "kootas": kootas,
        "total": total,
        "max": max_points,
        "auspicious": auspicious,
        "pending": (["vashya"] if vashya["points"] is None else []) + PENDING,
        "mangal": {
            "bride": K.status(b.chart, b.time_known) if b.chart else None,
            "groom": K.status(g.chart, g.time_known) if g.chart else None,
            "cancellation": K.cancellation(
                g.chart if g.time_known else None, b.chart if b.time_known else None
            ),
        },
        "notes": notes,
        "engine": provenance(),
    }
