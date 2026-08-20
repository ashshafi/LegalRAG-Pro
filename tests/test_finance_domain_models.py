from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from finance_domain.models import (
    COMPANY_SCHEMA_VERSION,
    FINANCE_WORKSPACE_SCHEMA_VERSION,
    SECURITY_SCHEMA_VERSION,
    Company,
    FinanceWorkspace,
    FinancialPeriod,
    FinancialPeriodType,
    Security,
    SecurityType,
    WorkspaceStatus,
)

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
COMPANY_ID = "22222222-2222-4222-8222-222222222222"
SECURITY_ID = "33333333-3333-4333-8333-333333333333"


def test_core_records_are_frozen_and_typed():
    workspace = FinanceWorkspace(
        schema_version=FINANCE_WORKSPACE_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        name="FIN-DEMO-001",
        status=WorkspaceStatus.ACTIVE,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    company = Company(
        schema_version=COMPANY_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        legal_name="TargetCo plc",
        display_name="TargetCo",
        country_code="GB",
        reporting_currency="GBP",
    )
    security = Security(
        schema_version=SECURITY_SCHEMA_VERSION,
        workspace_id=WORKSPACE_ID,
        security_id=SECURITY_ID,
        company_id=COMPANY_ID,
        security_type=SecurityType.COMMON_EQUITY,
        ticker="TGT",
        exchange_mic="XLON",
        currency="GBP",
    )
    assert workspace.status is WorkspaceStatus.ACTIVE
    assert company.reporting_currency == "GBP"
    assert security.security_type is SecurityType.COMMON_EQUITY
    with pytest.raises(FrozenInstanceError):
        company.display_name = "Changed"


def test_financial_period_holds_explicit_dates():
    period = FinancialPeriod(
        schema_version="financial-period/1.0",
        workspace_id=WORKSPACE_ID,
        company_id=COMPANY_ID,
        period_type=FinancialPeriodType.FY,
        label="FY2025",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        financial_period_id="sha256:" + "0" * 64,
    )
    assert period.start_date == date(2025, 1, 1)
    assert period.end_date == date(2025, 12, 31)
    assert Decimal("1.0") == Decimal("1")
