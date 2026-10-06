import pytest

from career_agents.compass import calculators as calc


def test_progressive():
    assert calc.progressive(50, [(10, 0.0), (30, 0.1), (None, 0.5)]) == pytest.approx(12.0)


def test_india_new_regime_with_surcharge_and_cess():
    # ₹1.8 Cr: slab tax ₹49.575L, +15% surcharge, +4% cess
    (tax,) = calc.tax_in(18_000_000).values()
    assert tax == pytest.approx(5_929_170, rel=1e-4)


def test_singapore_and_uae():
    assert calc.tax_sg(550_000)["income tax"] == pytest.approx(95_650)
    assert calc.tax_ae(1_000_000)["income tax"] == 0


def test_us_federal_mfj_and_washington():
    parts = calc.tax_us(492_000, "WA", "mfj")
    assert parts["federal income tax"] == pytest.approx(100_048, abs=1)
    assert parts["state/local"] == pytest.approx(0.0058 * 492_000)


def test_netherlands_ruling_lowers_tax():
    with_ruling = calc.tax_nl(220_000, 0.27)
    without = calc.tax_nl(220_000, 0.0)
    assert with_ruling["income tax + national insurance (box 1)"] < without["income tax + national insurance (box 1)"]
    assert with_ruling["_tax_free_allowance"] == pytest.approx(59_400)


def test_uk_personal_allowance_taper():
    assert calc.tax_uk(200_000)["income tax"] == pytest.approx(0.2 * 37_700 + 0.4 * (125_140 - 37_700) + 0.45 * (200_000 - 125_140))


def test_estimate_converts_currency_and_rejects_unknown_city():
    est = calc.estimate("singapore", 100_000, "USD")
    assert est.currency == "SGD" and est.gross_usd == pytest.approx(100_000, abs=2)
    with pytest.raises(KeyError):
        calc.estimate("atlantis", 1)


def test_compare_respects_weights():
    default_top = calc.compare()[0]["key"]
    parents_first = calc.compare(calc.parse_weights("parents=5"))[0]["key"]
    assert default_top == "bay_area"
    assert parents_first in {"dubai", "bengaluru"}
    with pytest.raises(KeyError):
        calc.parse_weights("vibes=1")


def test_evaluate_offer_against_current_and_target():
    result = calc.evaluate_offer("seattle", 260_000, "USD", bonus_pct=20, annual_equity=180_000)
    assert result["offer"]["gross_usd"] == 492_000
    assert result["vs_target_usd"] == 92_000
    assert "current" in result and result["savings_change_usd"] > 0
