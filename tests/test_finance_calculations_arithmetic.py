from decimal import Decimal
import pytest

from finance_calculations import ebitda_margin, enterprise_value, equity_value, multiple, net_debt, revenue_growth


def test_pure_decimal_arithmetic():
    assert revenue_growth(Decimal("1050"), Decimal("920")) == Decimal("1050") / Decimal("920") - Decimal(1)
    assert ebitda_margin(Decimal("225"), Decimal("1050")) == Decimal("225") / Decimal("1050")
    assert equity_value(Decimal("12.84"), Decimal("175")) == Decimal("2247.00")
    assert net_debt(Decimal("260"), Decimal("110")) == Decimal("150")
    assert enterprise_value(Decimal("12.84"), Decimal("175"), Decimal("260"), Decimal("110")) == Decimal("2397.00")
    assert multiple(Decimal("2397"), Decimal("1050")) == Decimal("2397") / Decimal("1050")


def test_division_by_zero_fails_closed():
    with pytest.raises(ZeroDivisionError):
        revenue_growth(Decimal("1"), Decimal("0"))
    with pytest.raises(ZeroDivisionError):
        ebitda_margin(Decimal("1"), Decimal("0"))
    with pytest.raises(ZeroDivisionError):
        multiple(Decimal("1"), Decimal("0"))
