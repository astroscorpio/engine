from collections import Counter

from conftest import EXAMPLE, call

from astro_compute import matching as M

GROOM = {"name": "G", "nakshatra": "rohini", "pada": 2}


def test_assignments_cover_every_nakshatra_as_the_sources_list_them():
    assert len(M.YONI_OF_NAKSHATRA) == len(M.GANA_OF_NAKSHATRA) == len(M.NADI_OF_NAKSHATRA) == 27
    yoni = Counter(M.YONI_OF_NAKSHATRA)
    assert all(yoni[y] == 2 for y in M.YONIS if y != "mongoose") and yoni["mongoose"] == 1
    assert Counter(M.GANA_OF_NAKSHATRA) == {"deva": 9, "manushya": 9, "rakshasa": 9}
    assert Counter(M.NADI_OF_NAKSHATRA) == {"adi": 9, "madhya": 9, "antya": 9}
    # MC 6.34: Ashwini, Ardra, Punarvasu, U.Phalguni, Hasta, Jyeshtha, Mula, Shatabhisha,
    # P.Bhadrapada.
    adi = [i for i, n in enumerate(M.NADI_OF_NAKSHATRA) if n == "adi"]
    assert adi == [0, 5, 6, 11, 12, 17, 18, 23, 24]
    assert Counter(M.VARNA_OF_SIGN.values()) == {
        "brahmana": 3,
        "kshatriya": 3,
        "vaishya": 3,
        "shudra": 3,
    }


def test_yoni_table_matches_the_printed_reading():
    p = M.YONI_PRINTED
    assert all(p[i][i] == 4 for i in range(14))
    asymmetric = {
        frozenset((M.YONIS[i], M.YONIS[j]))
        for i in range(14)
        for j in range(i + 1, 14)
        if p[i][j] is not None and p[j][i] is not None and p[i][j] != p[j][i]
    }
    assert len(asymmetric) == 19  # the 20 listed in the sources, less the damaged cow/buffalo cell
    for a, b in [
        ("horse", "buffalo"),
        ("lion", "elephant"),
        ("sheep", "monkey"),
        ("mongoose", "serpent"),
        ("deer", "dog"),
        ("cat", "rat"),
        ("tiger", "cow"),
    ]:  # mahavaira, MC 6.26
        assert M._yoni_points(a, b) == 0 == M._yoni_points(b, a), (a, b)
    assert M._yoni_points("cow", "buffalo") == 3
    assert M._yoni_points("serpent", "cat") == 1  # printed 1 one way, 3 the other: the lower


def test_graha_maitri_matrix_is_the_one_derived_in_the_sources():
    order = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]
    expected = [
        [5, 5, 5, 4, 5, 0, 0],
        [5, 5, 4, 1, 4, 0.5, 0.5],
        [5, 4, 5, 0.5, 5, 3, 0.5],
        [4, 1, 0.5, 5, 0.5, 5, 4],
        [5, 4, 5, 0.5, 5, 0.5, 3],
        [0, 0.5, 3, 5, 0.5, 5, 5],
        [0, 0.5, 0.5, 4, 3, 5, 5],
    ]
    assert [[M.maitri_points(a, b) for b in order] for a in order] == expected


def test_tara_counts_inclusively_both_ways():
    assert M._tara(0, 0) == 1  # same star: janma
    assert M._tara(0, 2) == 3  # Ashwini -> Krittika is the 3rd: vipat
    assert M._tara(2, 0) == 26 % 9  # 26th counting on round the circle
    assert M._tara(0, 8) == 9  # remainder 0 reads as 9


def test_match_from_a_chart_and_a_birth_star():
    status, out = call("POST", "/v1/matching", body={"bride": EXAMPLE, "groom": GROOM})
    assert status == 200, out
    ids = [k["id"] for k in out["kootas"]]
    assert ids == ["varna", "vashya", "tara", "yoni", "graha_maitri", "gana", "bhakoot", "nadi"]
    scored = [k for k in out["kootas"] if not k["pending"]]
    assert out["total"] == sum(k["points"] for k in scored)
    assert out["max"] == 36 and out["pending"] == []
    assert out["mangal"]["groom"] is None  # known only by birth star
    assert out["mangal"]["bride"]["rule"] == "khankhoje_1943"
    assert out["mangal"]["cancellation"] is None
    assert all(0 <= k["points"] <= k["max"] and k["source"] for k in scored)
    assert out["bride"]["moonSign"] == "scorpio" and out["bride"]["nakshatra"] == "anuradha"
    assert out["groom"] == {
        "name": "G", "moonSign": "taurus", "nakshatra": "rohini", "pada": 2,
        "navamshaSign": "taurus", "basis": "nakshatra", "moonUncertain": False, "nameReading": None,
    }  # fmt: skip
    assert out["auspicious"] == (out["total"] > 18)


def test_scorpio_taurus_is_samasaptaka_and_gana_follows_direction():
    status, out = call("POST", "/v1/matching", body={"bride": EXAMPLE, "groom": GROOM})
    k = {row["id"]: row for row in out["kootas"]}
    assert k["bhakoot"]["detail"] == "1/7" and k["bhakoot"]["points"] == 7
    # Anuradha is deva, Rohini manushya: groom manushya x bride deva = 4; reversed roles = 5.
    assert k["gana"]["points"] == 4
    status, rev = call(
        "POST",
        "/v1/matching",
        body={
            "bride": {"nakshatra": "rohini", "pada": 2},
            "groom": {"nakshatra": "anuradha", "pada": 2},
        },
    )
    assert {r["id"]: r for r in rev["kootas"]}["gana"]["points"] == 5


def test_nadi_exceptions_and_same_star_same_pada():
    # Krittika pada 2 is Taurus, pada 1 is Aries: same star, different signs,
    # so MC 6.36 lifts the nadi dosha.
    body = {
        "bride": {"nakshatra": "krittika", "pada": 1},
        "groom": {"nakshatra": "krittika", "pada": 2},
    }
    status, out = call("POST", "/v1/matching", body=body)
    nadi = {r["id"]: r for r in out["kootas"]}["nadi"]
    assert nadi["points"] == 0 and nadi["dosha"] and nadi["cancelled"]
    assert nadi["note"] == "same_nakshatra_different_sign"
    body = {
        "bride": {"nakshatra": "rohini", "pada": 3},
        "groom": {"nakshatra": "rohini", "pada": 3},
    }
    status, out = call("POST", "/v1/matching", body=body)
    nadi = {r["id"]: r for r in out["kootas"]}["nadi"]
    assert nadi["dosha"] and not nadi["cancelled"] and "same_nakshatra_same_pada" in out["notes"]


def test_bhakoot_cancellation_needs_nadi_clear():
    # Aries (Ashwini) and Scorpio (Anuradha) are 6/8 with the same lord, Mars.
    body = {
        "bride": {"nakshatra": "ashwini", "pada": 1},
        "groom": {"nakshatra": "anuradha", "pada": 1},
    }
    status, out = call("POST", "/v1/matching", body=body)
    k = {r["id"]: r for r in out["kootas"]}
    assert k["bhakoot"]["detail"] == "6/8" and k["bhakoot"]["dosha"]
    assert k["nadi"]["dosha"] is False  # adi vs madhya
    assert k["bhakoot"]["cancelled"] and k["bhakoot"]["note"] == "same_sign_lord"


def test_bad_partner_input_names_the_field():
    status, out = call(
        "POST", "/v1/matching", body={"bride": EXAMPLE, "groom": {"nakshatra": "rohini", "pada": 7}}
    )
    assert status == 400 and out["error"]["field"] == "groom.pada"
    status, out = call(
        "POST", "/v1/matching", body={"bride": EXAMPLE, "groom": {"nakshatra": "pluto", "pada": 1}}
    )
    assert status == 400 and out["error"]["field"] == "groom.nakshatra"


def test_vashya_groups_follow_our_reading_of_bjs():
    assert [M.vashya_group(s, 5) for s in range(12)] == [
        "chatushpada", "chatushpada", "manava", "keeta", "vanachara", "manava",
        "manava", "keeta", "manava", "chatushpada", "jalachara", "jalachara",
    ]  # fmt: skip
    assert M.vashya_group(8, 20) == "chatushpada" and M.vashya_group(9, 20) == "jalachara"
    table = M.VASHYA_POINTS
    assert all(table[i][j] == table[j][i] for i in range(5) for j in range(5))


def test_vashya_open_when_a_star_pada_straddles_15_degrees():
    # P.Ashadha pada 1 runs Sagittarius 13°20' to 16°40', across the split.
    body = {
        "bride": {"nakshatra": "purva_ashadha", "pada": 1},
        "groom": {"nakshatra": "rohini", "pada": 2},
    }
    status, out = call("POST", "/v1/matching", body=body)
    vashya = {r["id"]: r for r in out["kootas"]}["vashya"]
    assert vashya["points"] is None and vashya["note"] == "vashya_group_uncertain"
    assert out["max"] == 34


def test_yoni_gender_and_enmity_notes():
    # JN p. 142, v. 10: Bharani is a female elephant, Dhanishtha a male lion; the
    # lion and the elephant are great enemies (MC 6.25-26), so v. 12 says avoid.
    status, out = call(
        "POST",
        "/v1/matching",
        body={
            "bride": {"nakshatra": "bharani", "pada": 1},
            "groom": {"nakshatra": "dhanishta", "pada": 1},
        },
    )
    assert status == 200, out
    yoni = next(k for k in out["kootas"] if k["id"] == "yoni")
    assert yoni["genders"] == {"bride": "female", "groom": "male"} and yoni["points"] == 0
    assert yoni["note"] == "yoni_enmity_opposite_gender" and yoni["note"] in out["notes"]
    # Ashwini (horse) and Hasta (buffalo) are both male: middling.
    status, out = call(
        "POST",
        "/v1/matching",
        body={
            "bride": {"nakshatra": "ashwini", "pada": 1},
            "groom": {"nakshatra": "hasta", "pada": 1},
        },
    )
    yoni = next(k for k in out["kootas"] if k["id"] == "yoni")
    assert yoni["note"] == "yoni_enmity_same_gender"
    assert sum(M.yoni_gender(i) == "female" for i in range(27)) == 6
