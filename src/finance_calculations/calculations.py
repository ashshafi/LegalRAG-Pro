"""Pure Decimal arithmetic for Finance F3. No LLM arithmetic is permitted."""

from __future__ import annotations

from decimal import Decimal


def revenue_growth(current_revenue: Decimal, prior_revenue: Decimal) -> Decimal:
    if prior_revenue == 0:
        raise ZeroDivisionError("prior revenue is zero.")
    return current_revenue / prior_revenue - Decimal(1)


def ebitda_margin(ebitda: Decimal, revenue: Decimal) -> Decimal:
    if revenue == 0:
        raise ZeroDivisionError("revenue is zero.")
    return ebitda / revenue


def equity_value(share_price: Decimal, shares_outstanding: Decimal) -> Decimal:
    return share_price * shares_outstanding


def net_debt(gross_debt: Decimal, cash: Decimal) -> Decimal:
    return gross_debt - cash


def enterprise_value(
    share_price: Decimal,
    shares_outstanding: Decimal,
    gross_debt: Decimal,
    cash: Decimal,
) -> Decimal:
    return equity_value(share_price, shares_outstanding) + net_debt(gross_debt, cash)


def multiple(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        raise ZeroDivisionError("multiple denominator is zero.")
    return numerator / denominator


__all__ = [
    "ebitda_margin",
    "enterprise_value",
    "equity_value",
    "multiple",
    "net_debt",
    "revenue_growth",
]
