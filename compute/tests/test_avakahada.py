import pytest
from conftest import EXAMPLE, call

from astro_compute import avakahada as A


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


def test_the_texts_own_examples():
    # MM v.55 commentary: Pradyumna is looked up by pa. AC p. 23: Mrigashira pada 3 gives
    # ka (Kamalakanta, Kalidatta).
    out = A.lookup("प्रद्युम्न")
    assert (out["nakshatra"], out["pada"], out["syllable"]) == ("uttara_phalguni", 3, "pa")
    assert out["rules"] == ["conjunct_first_letter"] and out["exact"]
    assert at("कमलाकान्त") == at("कालीदत्त") == ("mrigashira", 3)
    assert at("Pradyumna") == ("uttara_phalguni", 3)
    assert at("Kamalakanta") == ("mrigashira", 3)


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
        ("अर्जुन", "krittika", 1, []),
        ("ओम", "rohini", 1, []),
    ],
)
def test_devanagari_rules(name, star, pada, rules):
    out = A.lookup(name)
    assert (out["nakshatra"], out["pada"], out["rules"]) == (star, pada, rules), out


@pytest.mark.parametrize(
    "name, why",
    [
        ("ज़ोया", "has no letter"),  # nukta sound
        ("कृष्ण", "vowel 'ṛ'"),
        ("ऐश्वर्या", "vowel 'ai'"),
        ("Zoya", "'za' has no letter"),
        ("Farhan", "'fa' has no letter"),
        ("Aishwarya", "vowel 'ai'"),
        ("Dhruv", "no syllable 'dhu'"),
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
        {"syllable": "ḍi", "devanagari": "डी", "nakshatra": "ashlesha", "pada": 1}
    ]
    assert not out["exact"]
    out = A.lookup("Shiva")
    assert (out["nakshatra"], out["pada"], out["syllableRead"]) == ("shatabhisha", 3, "śi")
    assert [a["nakshatra"] for a in out["alternatives"]] == ["shravana"]  # as ssi -> khi
    out = A.lookup("Thiru")  # th for the dental t, as in South Indian spellings
    assert (out["nakshatra"], out["pada"], out["syllableRead"]) == ("vishakha", 1, "ti")
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
        "groom": {"nakshatra": "rohini", "pada": 2},
    }
    status, out = call("POST", "/v1/matching", body=body)
    assert status == 200, out
    bride = out["bride"]
    assert (
        bride["basis"] == "name" and bride["nakshatra"] == "uttara_phalguni" and bride["pada"] == 4
    )
    assert bride["moonSign"] == "virgo" and bride["navamshaSign"] == "pisces"
    assert bride["nameReading"]["syllable"] == "pi" and "matched" not in bride["nameReading"]
    assert out["groom"]["nameReading"] is None
    assert out["mangal"]["bride"] is None
    status, out = call(
        "POST", "/v1/matching", body={"bride": EXAMPLE, "groom": {"name": "Juhi", "basis": "name"}}
    )
    assert (
        status == 200
        and out["groom"]["nakshatra"] == "uttara_ashadha"
        and out["groom"]["pada"] == 4
    )


def test_unreadable_name_is_a_422_naming_the_field():
    body = {"bride": {"name": "Zoya", "basis": "name"}, "groom": {"nakshatra": "rohini", "pada": 2}}
    status, out = call("POST", "/v1/matching", body=body)
    assert status == 422 and out["error"]["code"] == "name_not_in_chakra"
    assert out["error"]["field"] == "bride.name" and "birth star" in out["error"]["message"]
    # Without basis "name" a lone name is an incomplete chart input, never a silent name match.
    status, out = call("POST", "/v1/matching", body={"bride": {"name": "Priya"}, "groom": EXAMPLE})
    assert status == 400 and out["error"]["field"] == "bride.date"
