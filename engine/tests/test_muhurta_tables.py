"""Muhurta tables against Muhurta Chintamani (1945 printing) and Nirnaya-sindhu (1898)."""

from jyotisha import muhurta as Mu
from jyotisha import rare as R


def test_sarvartha_siddhi_follows_mc_1_28_29():
    assert R.SARVARTHA_SIDDHI[2] == {"Ashwini", "U.Bhadrapada", "Krittika", "Ashlesha"}  # Tuesday
    assert "P.Phalguni" in R.SARVARTHA_SIDDHI[5] and "Anuradha" not in R.SARVARTHA_SIDDHI[5]
    assert R.SARVARTHA_SIDDHI_VARIANT == {5: {"Anuradha"}}


def test_inauspicious_yoga_spans_follow_mc_1_34_35():
    assert Mu.BAD_YOGA_GHATIS["Vajra"] == 3  # MC and NS; Muhurta Martanda alone gives 9
    assert Mu.BAD_YOGA_GHATIS["Parigha"] == "half"
    assert Mu.BAD_YOGA_GHATIS["Vyatipata"] is None and Mu.BAD_YOGA_GHATIS["Vaidhriti"] is None


def test_siddhi_pairs_visha_tithis_and_act_bans():
    # MC 1.20-21: Sun-Hasta/5 ... Sat-Rohini/11; MC 1.22: house, journey, marriage.
    assert [R.AMRITA_VISHA_TITHI[w] for w in range(7)] == [5, 6, 7, 8, 9, 10, 11]
    assert R.AMRITA_ACT_BANS == {"home": 2, "travel": 6, "marriage": 4}
    assert R.AMRITA_SIDDHI[4] == "Pushya" and R.AMRITA_SIDDHI[2] == "Ashwini"
