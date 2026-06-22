"""Black-Scholes Greeks calculator.

Ported from OptionsAI/options_monitor_agent/tools/greeks_calculator.py
Uses pure math (no scipy dependency).
"""

import math


# Default market parameters
RISK_FREE_RATE = 0.053  # 5.3% US rate
DIVIDEND_YIELD = 0.013  # 1.3% average
TRADING_DAYS = 252

_SQRT_2PI = math.sqrt(2 * math.pi)


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def calculate_greeks(
    S: float,
    K: float,
    T: float,
    sigma: float,
    option_type: str = "call",
    r: float = RISK_FREE_RATE,
    q: float = DIVIDEND_YIELD,
) -> dict:
    """Calculate Black-Scholes Greeks for a single option.

    Args:
        S: Underlying price
        K: Strike price
        T: Time to expiration in years
        sigma: Implied volatility (decimal, e.g. 0.185 = 18.5%)
        option_type: "call" or "put"
        r: Risk-free rate
        q: Dividend yield

    Returns:
        Dict with delta, gamma, theta (daily), vega (per 1% IV), rho, theoretical_price
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return {
            "delta": 0, "gamma": 0, "theta": 0,
            "vega": 0, "rho": 0, "theoretical_price": 0,
        }

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    exp_qT = math.exp(-q * T)
    exp_rT = math.exp(-r * T)
    pdf_d1 = _norm_pdf(d1)

    # Common
    gamma = pdf_d1 * exp_qT / (S * sigma * sqrt_T)
    vega = S * exp_qT * sqrt_T * pdf_d1 / 100  # per 1% IV change

    if option_type.lower() == "call":
        delta = exp_qT * _norm_cdf(d1)
        theta = (
            -(S * exp_qT * pdf_d1 * sigma) / (2 * sqrt_T)
            - r * K * exp_rT * _norm_cdf(d2)
            + q * S * exp_qT * _norm_cdf(d1)
        )
        rho = K * T * exp_rT * _norm_cdf(d2)
        price = S * exp_qT * _norm_cdf(d1) - K * exp_rT * _norm_cdf(d2)
    else:
        delta = exp_qT * (_norm_cdf(d1) - 1)
        theta = (
            -(S * exp_qT * pdf_d1 * sigma) / (2 * sqrt_T)
            + r * K * exp_rT * _norm_cdf(-d2)
            - q * S * exp_qT * _norm_cdf(-d1)
        )
        rho = -K * T * exp_rT * _norm_cdf(-d2)
        price = K * exp_rT * _norm_cdf(-d2) - S * exp_qT * _norm_cdf(-d1)

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta / TRADING_DAYS, 4),  # daily
        "vega": round(vega / 100, 4),  # per 1% IV
        "rho": round(rho / 100, 4),
        "theoretical_price": round(price, 4),
    }


def enrich_options_with_greeks(options_data: dict, r: float = RISK_FREE_RATE) -> dict:
    """Add Greeks to each option in the chain.

    `r` is the annualized risk-free rate; callers resolve it per option
    currency (see services.fred_rates). Defaults to the USD constant so
    behaviour is unchanged when no rate is supplied.
    """
    S = options_data.get("current_price", 0)
    if not S:
        return options_data

    for option in options_data.get("calls", []) + options_data.get("puts", []):
        K = option.get("strike", 0)
        iv = option.get("impliedVolatility", 0)
        days = option.get("daysToExpiry", 1)
        T = days / 365.0

        if K > 0 and iv > 0:
            option["greeks"] = calculate_greeks(S, K, T, iv, option["type"].lower(), r=r)
        else:
            option["greeks"] = {}

    return options_data
