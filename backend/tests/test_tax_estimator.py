"""Tests for the savings-base IRPF estimator (pure math, no DB).

These pin the ENGINE behaviour against the 2024 rate tables encoded in
tax_estimator. They do not assert the rates are legally current — that is a
separate AEAT verification step before launch.
"""

from decimal import Decimal

from backend.services.tax_estimator import (
    SavingsInputs,
    TaxpayerProfile,
    compensate,
    estimate_savings,
    personal_minimum,
    progressive_tax,
    resolve_year,
)

D = Decimal


def test_resolve_year_falls_back_to_latest():
    assert resolve_year(2024) == 2024
    assert resolve_year(2099) == 2024  # not encoded → latest available
    assert resolve_year(1990) == 2024


def test_progressive_tax_brackets():
    # 8000 → 6000@19% + 2000@21% = 1140 + 420 = 1560
    tax, detail = progressive_tax(D("8000"), 2024)
    assert tax == D("1560")
    assert len(detail) == 2

    # exactly first bracket
    tax, _ = progressive_tax(D("6000"), 2024)
    assert tax == D("1140")

    # crosses into 23% band: 6000@19 + 44000@21 + 10000@23 = 1140 + 9240 + 2300
    tax, _ = progressive_tax(D("60000"), 2024)
    assert tax == D("12680")


def test_progressive_tax_zero_or_negative():
    assert progressive_tax(D("0"), 2024)[0] == D("0")
    assert progressive_tax(D("-500"), 2024)[0] == D("0")


def test_compensate_both_positive():
    base, rcm_cf, gp_cf = compensate(D("1000"), D("500"), 2024)
    assert base == D("1500")
    assert rcm_cf == D("0") and gp_cf == D("0")


def test_compensate_negative_gp_capped_at_25pct():
    # rcm 10000, gp -2000 → comp = min(2000, 2500) = 2000 → base 8000, gp fully used
    base, rcm_cf, gp_cf = compensate(D("10000"), D("-2000"), 2024)
    assert base == D("8000")
    assert gp_cf == D("0")

    # rcm 10000, gp -4000 → comp capped at 2500 → base 7500, gp carries -1500
    base, rcm_cf, gp_cf = compensate(D("10000"), D("-4000"), 2024)
    assert base == D("7500")
    assert gp_cf == D("-1500")


def test_compensate_both_negative_base_zero():
    base, rcm_cf, gp_cf = compensate(D("-1000"), D("-2000"), 2024)
    assert base == D("0")
    assert rcm_cf == D("-1000") and gp_cf == D("-2000")


def test_personal_minimum_age_and_disability():
    assert personal_minimum(TaxpayerProfile(), 2024) == D("5550")
    assert personal_minimum(TaxpayerProfile(age=66), 2024) == D("6700")
    assert personal_minimum(TaxpayerProfile(age=80), 2024) == D("8100")  # +1150 +1400
    assert personal_minimum(TaxpayerProfile(disability="severe"), 2024) == D("14550")


def test_personal_minimum_descendants_tiered():
    # base + 2400 + 2700 + 4000 = 14650
    assert personal_minimum(TaxpayerProfile(descendants=3), 2024) == D("14650")


def test_estimate_small_savings_fully_covered_by_minimum():
    # No general base → full 5550 minimum on savings; base 1000 < minimum → quota 0
    est = estimate_savings(
        SavingsInputs(rcm_net=D("1000"), withholdings=D("190")),
        TaxpayerProfile(),
        2024,
    )
    assert est.savings_base == D("1000")
    assert est.quota == D("0")
    assert est.result == D("-190")  # withholding refunded


def test_estimate_with_general_base_absorbing_minimum():
    # general base 20000 absorbs the 5550 minimum → none on savings
    est = estimate_savings(
        SavingsInputs(rcm_net=D("10000"), withholdings=D("1900")),
        TaxpayerProfile(general_base=D("20000")),
        2024,
    )
    assert est.minimum_on_savings == D("0")
    assert est.gross_quota == D("1980")  # 6000@19 + 4000@21
    assert est.quota == D("1980")
    assert est.result == D("80")  # a ingresar


def test_estimate_with_loss_compensation():
    est = estimate_savings(
        SavingsInputs(rcm_net=D("10000"), gains=D("0"), losses=D("-2000"),
                      withholdings=D("0")),
        TaxpayerProfile(general_base=D("20000")),
        2024,
    )
    assert est.savings_base == D("8000")
    assert est.gross_quota == D("1560")


def test_estimate_rates_year_used_exposed():
    est = estimate_savings(SavingsInputs(rcm_net=D("100")), TaxpayerProfile(), 2030)
    assert est.rates_year_used == 2024
