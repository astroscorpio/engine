import pytest
from conftest import EXAMPLE, call

from astro_compute import avakahada as A

STAR = {"nakshatra": "rohini", "pada": 2}


def at(name: str) -> tuple[str, int]:
    out = A.lookup(name)
    assert out["matched"], out
    return out["nakshatra"], out["pada"]


def test_chakra_has_112_distinct_cells_with_abhijit_in_uttara_ashadha():
    assert len(A.TABLE) == 112 and len(A.CHAKRA) == 28
    abhijit = [k for k, c in A.TABLE.items() if c.abhijit]
    assert sorted(abhijit) == [("j", "e"), ("j", "o"), ("j", "u"), ("kh", "a")]
    assert all(A.TABLE[k].nakshatra == "uttara_ashadha" and A.TABLE[k].pada == 4 for k in abhijit)
    assert A.CHAKRA[5]["padas"][2] == {"pada": 3, "syllable": "ṅa", "devanagari": "ङ"}
    singles = {"gh", "ng", "ch", "ss", "nn", "tth", "dh", "ph", "ddh", "th", "jh", "ny"}
    assert set(A.SINGLE) == singles


def test_the_texts_own_examples():
    # MM v.55 commentary: Pradyumna pa, Priyavacana pi, Drupada du, Sridhara si,
    # Kshetrajna ke. AC p. 23: Mrigashira 3 gives ka (Kamalakanta, Kalidatta);
    # AC p. 25: Riddhinatha is Chitra (pada 3); AC p. 26: Amaranatha and
    # Adityaprasada are both Krittika 1.
    out = A.lookup("प्रद्युम्न")
    assert (out["nakshatra"], out["pada"], out["syllable"]) == ("uttara_phalguni", 3, "pa")
    assert out["rules"] == ["conjunct_first_letter"] and out["exact"]
    assert at("प्रियवचन") == ("uttara_phalguni", 4)
    assert at("द्रुपद") == ("uttara_bhadrapada", 1)
    assert at("श्रीधर") == ("shatabhisha", 3)
    assert at("क्षेत्रज्ञ") == ("punarvasu", 1)
    assert at("कमलाकान्त") == at("कालीदत्त") == ("mrigashira", 3)
    out = A.lookup("ऋद्धिनाथ")
    assert (out["nakshatra"], out["pada"], out["rules"]) == ("chitra", 3, ["r_vowel_as_ra"])
    assert at("अमरनाथ") == at("आदित्यप्रसाद") == ("krittika", 1)
    assert at("Pradyumna") == ("uttara_phalguni", 3)


@pytest.mark.parametrize(
    "name, star, pada, rules",
    [
        ("क्षितिज", "mrigashira", 4, ["conjunct_first_letter"]),  # क्ष -> क
        ("त्रिलोक", "vishakha", 1, ["conjunct_first_letter"]),  # त्र -> त
        ("ज्ञानेश", "uttara_ashadha", 3, ["conjunct_first_letter"]),  # ज्ञ -> ज
        ("बलराम", "rohini", 2, ["equivalent_letters"]),  # ba = va
        ("शिव", "shatabhisha", 3, ["equivalent_letters"]),  # sha = sa
        ("षण्मुख", "hasta", 2, []),  # ssa is in the chakra itself
        ("षोडश", "shravana", 4, ["equivalent_letters"]),  # sso is not: kha = ssa
        ("जुगल", "uttara_ashadha", 4, ["abhijit_as_uttara_ashadha"]),
        ("ङ", "dhanishta", 1, ["nasal_read_as"]),  # nga read as ga
        ("णमो", "pushya", 4, ["nasal_read_as"]),  # nna read as dda
        ("ऐश्वर्या", "krittika", 4, ["vowel_pairs"]),  # ai = e
        ("गौरव", "shatabhisha", 1, ["vowel_pairs"]),  # au = o
        ("अर्जुन", "krittika", 1, []),
        ("ओम", "rohini", 1, []),
    ],
)
def test_devanagari_rules(name, star, pada, rules):
    out = A.lookup(name)
    assert (out["nakshatra"], out["pada"], out["rules"]) == (star, pada, rules), out
    assert out["exact"] and not out["ourReading"]


@pytest.mark.parametrize(
    "name, star, pada, rules",
    [
        # kr is read as kra, then the conjunct's first letter: ka (our reading)
        ("कृष्ण", "mrigashira", 3, ["r_in_syllable_as_ra", "conjunct_first_letter"]),
        # dha is the only dh cell; dhru takes it (our reading)
        ("ध्रुव", "purva_ashadha", 2, ["conjunct_first_letter", "single_cell_consonant"]),
        ("धीरज", "purva_ashadha", 2, ["single_cell_consonant"]),
    ],
)
def test_our_readings_are_labelled_and_inexact(name, star, pada, rules):
    out = A.lookup(name)
    assert (out["nakshatra"], out["pada"], out["rules"]) == (star, pada, rules), out
    assert out["ourReading"] and not out["exact"]


@pytest.mark.parametrize(
    "name, why",
    [
        ("ज़ोया", "has no letter"),  # nukta sound
        ("Zoya", "'za' has no letter"),
        ("Farhan", "'fa' has no letter"),
        ("రాము", "Latin or Devanagari"),
    ],
)
def test_unmatched_names_say_why(name, why):
    out = A.lookup(name)
    assert not out["matched"] and why in out["reason"], out


def test_latin_spellings_list_the_other_readings():
    out = A.lookup("Deepak")
    assert (out["nakshatra"], out["pada"], out["syllable"]) == ("purva_bhadrapada", 4, "di")
    assert out["alternatives"] == [
        {
            "syllable": "ḍi",
            "devanagari": "डी",
            "nakshatra": "ashlesha",
            "pada": 1,
            "ourReading": False,
        }
    ]
    assert not out["exact"]
    out = A.lookup("Shiva")
    assert (out["nakshatra"], out["pada"], out["syllableRead"]) == ("shatabhisha", 3, "śi")
    assert [a["nakshatra"] for a in out["alternatives"]] == ["shravana"]  # as ssi -> khi
    # th for the dental t, as in South Indian spellings: the cited reading comes
    # before the single-cell readings of tha and ttha.
    out = A.lookup("Thiru")
    assert (out["nakshatra"], out["pada"], out["syllableRead"]) == ("vishakha", 1, "ti")
    assert not out["ourReading"] and all(a["ourReading"] for a in out["alternatives"])
    out = A.lookup("Gyan")
    assert (out["nakshatra"], out["pada"]) == ("uttara_ashadha", 3)
    assert out["alternatives"][0]["nakshatra"] == "dhanishta"


@pytest.mark.parametrize(
    "name, star, pada",
    [
        ("Bharat", "mula", 3),
        ("Juhi", "uttara_ashadha", 4),
        ("Kshitij", "mrigashira", 4),
        ("Chhavi", "ardra", 4),
        ("Chandra", "revati", 3),
        ("Brijesh", "rohini", 3),
        ("Shreya", "purva_bhadrapada", 1),
        ("Aarav", "krittika", 1),
        ("Esha", "krittika", 4),
        ("Wendy", "mrigashira", 1),
        ("Aishwarya", "krittika", 4),
        ("Gaurav", "shatabhisha", 1),
        ("Dhruv", "purva_ashadha", 2),
        ("Priya Sharma", "uttara_phalguni", 4),
    ],
)
def test_latin_names(name, star, pada):
    assert at(name) == (star, pada)


def test_the_first_word_is_read():
    assert A.lookup("Priya Sharma")["nameUsed"] == "Priya"


def test_match_by_name():
    body = {
        "bride": {"name": "Priya", "basis": "name"},
        "groom": {"name": "बलराम", "basis": "name"},
    }
    status, out = call("POST", "/v1/matching", body=body)
    assert status == 200, out
    bride = out["bride"]
    assert (
        bride["basis"] == "name" and bride["nakshatra"] == "uttara_phalguni" and bride["pada"] == 4
    )
    assert bride["moonSign"] == "virgo" and bride["navamshaSign"] == "pisces"
    assert bride["nameReading"]["syllable"] == "pi" and "matched" not in bride["nameReading"]
    assert out["groom"]["nameReading"]["rules"] == ["equivalent_letters"]
    assert out["basisRule"] == "mm_v54_both_by_name"
    assert out["mangal"]["bride"] is None and out["mangal"]["groom"] is None


def test_mm_v54_one_name_puts_both_partners_on_their_names():
    # The chart partner is read by its name too; its chart still gives its mangal.
    body = {"bride": EXAMPLE, "groom": {"name": "Juhi", "basis": "name"}}
    status, out = call("POST", "/v1/matching", body=body)
    assert status == 200, out
    assert out["basisRule"] == "mm_v54_both_by_name"
    assert out["bride"]["basis"] == "name" and out["bride"]["nameReading"]["nameUsed"] == "Example"
    assert (out["bride"]["nakshatra"], out["bride"]["pada"]) == ("krittika", 4)
    assert (out["groom"]["nakshatra"], out["groom"]["pada"]) == ("uttara_ashadha", 4)
    assert out["mangal"]["bride"]["rule"] == "khankhoje_1943"
    body = {"bride": {**STAR, "name": "Om"}, "groom": {"name": "Juhi", "basis": "name"}}
    status, out = call("POST", "/v1/matching", body=body)
    assert status == 200 and (out["bride"]["nakshatra"], out["bride"]["pada"]) == ("rohini", 1)
    # Without a name the other partner cannot be read.
    nameless = {k: v for k, v in EXAMPLE.items() if k != "name"}
    status, out = call(
        "POST", "/v1/matching", body={"bride": nameless, "groom": {"name": "Juhi", "basis": "name"}}
    )
    assert status == 422 and out["error"]["code"] == "name_required"
    assert out["error"]["field"] == "bride.name" and "v.54" in out["error"]["message"]
    status, out = call("POST", "/v1/matching", body={"bride": EXAMPLE, "groom": STAR})
    assert status == 200 and out["basisRule"] is None and out["bride"]["basis"] == "chart"


def test_unreadable_name_is_a_422_naming_the_field():
    body = {"bride": {"name": "Zoya", "basis": "name"}, "groom": {"name": "Om", "basis": "name"}}
    status, out = call("POST", "/v1/matching", body=body)
    assert status == 422 and out["error"]["code"] == "name_not_in_chakra"
    assert out["error"]["field"] == "bride.name" and "birth star" in out["error"]["message"]
    # Without basis "name" a lone name is an incomplete chart input, never a silent name match.
    status, out = call("POST", "/v1/matching", body={"bride": {"name": "Priya"}, "groom": EXAMPLE})
    assert status == 400 and out["error"]["field"] == "bride.date"
