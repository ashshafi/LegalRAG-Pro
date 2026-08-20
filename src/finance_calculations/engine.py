"""Deterministic F3 calculation authority over governed source facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Final

from finance_data import FinancialDataProvider
from finance_domain import FinancialFact, derive_finance_id

from .calculations import ebitda_margin, enterprise_value, equity_value, multiple, net_debt, revenue_growth
from .facts import FactResolution, resolve_financial_fact
from .models import (
    AnalyticalStatus,
    CALCULATION_RESULT_SCHEMA_VERSION,
    CALCULATION_VERSION,
    CalculationClassification,
    CalculationResult,
    ValueClassification,
)
from .serialization import calculation_result_identity_payload_to_dict
from .validation import validate_calculation_result

SUPPORTED_METRICS: Final[tuple[str, ...]] = (
    "EBITDA_MARGIN",
    "ENTERPRISE_VALUE",
    "EQUITY_VALUE",
    "EV_EBITDA",
    "EV_REVENUE",
    "NET_DEBT",
    "NET_DEBT_EBITDA",
    "PE_RATIO",
    "REVENUE_GROWTH",
)


@dataclass(frozen=True, slots=True)
class _InputRequest:
    name: str
    metric_code: str
    period: str
    security_bound: bool = False


@dataclass(frozen=True, slots=True)
class _MetricSpec:
    calculation_code: str
    formula: str
    requests: tuple[_InputRequest, ...]
    output_unit: str
    output_period: str | None
    evaluator: Callable[[dict[str, FinancialFact]], Decimal]
    currency_source: str | None


def _ev(facts: dict[str, FinancialFact]) -> Decimal:
    return enterprise_value(
        facts["price"].value,
        facts["shares"].value,
        facts["debt"].value,
        facts["cash"].value,
    )


def _specs() -> dict[str, _MetricSpec]:
    current = "current"
    prior = "prior"
    none = "none"
    return {
        "REVENUE_GROWTH": _MetricSpec(
            "CALC.REVENUE_GROWTH",
            "current_revenue / prior_revenue - 1",
            (_InputRequest("current_revenue", "REVENUE", current), _InputRequest("prior_revenue", "REVENUE", prior)),
            "ratio", current,
            lambda f: revenue_growth(f["current_revenue"].value, f["prior_revenue"].value),
            None,
        ),
        "EBITDA_MARGIN": _MetricSpec(
            "CALC.EBITDA_MARGIN",
            "ebitda / revenue",
            (_InputRequest("ebitda", "EBITDA", current), _InputRequest("revenue", "REVENUE", current)),
            "ratio", current,
            lambda f: ebitda_margin(f["ebitda"].value, f["revenue"].value),
            None,
        ),
        "EQUITY_VALUE": _MetricSpec(
            "CALC.EQUITY_VALUE",
            "share_price * shares_outstanding",
            (_InputRequest("price", "SHARE_PRICE", none, True), _InputRequest("shares", "SHARES_OUTSTANDING", none, True)),
            "million_currency", None,
            lambda f: equity_value(f["price"].value, f["shares"].value),
            "price",
        ),
        "NET_DEBT": _MetricSpec(
            "CALC.NET_DEBT",
            "gross_debt - cash",
            (_InputRequest("debt", "GROSS_DEBT", current), _InputRequest("cash", "CASH", current)),
            "million_currency", current,
            lambda f: net_debt(f["debt"].value, f["cash"].value),
            "debt",
        ),
        "ENTERPRISE_VALUE": _MetricSpec(
            "CALC.ENTERPRISE_VALUE",
            "share_price * shares_outstanding + gross_debt - cash",
            (_InputRequest("price", "SHARE_PRICE", none, True), _InputRequest("shares", "SHARES_OUTSTANDING", none, True), _InputRequest("debt", "GROSS_DEBT", current), _InputRequest("cash", "CASH", current)),
            "million_currency", current, _ev, "price",
        ),
        "EV_REVENUE": _MetricSpec(
            "CALC.EV_REVENUE",
            "(share_price * shares_outstanding + gross_debt - cash) / revenue",
            (_InputRequest("price", "SHARE_PRICE", none, True), _InputRequest("shares", "SHARES_OUTSTANDING", none, True), _InputRequest("debt", "GROSS_DEBT", current), _InputRequest("cash", "CASH", current), _InputRequest("denominator", "REVENUE", current)),
            "multiple", current,
            lambda f: multiple(_ev(f), f["denominator"].value), None,
        ),
        "EV_EBITDA": _MetricSpec(
            "CALC.EV_EBITDA",
            "(share_price * shares_outstanding + gross_debt - cash) / ebitda",
            (_InputRequest("price", "SHARE_PRICE", none, True), _InputRequest("shares", "SHARES_OUTSTANDING", none, True), _InputRequest("debt", "GROSS_DEBT", current), _InputRequest("cash", "CASH", current), _InputRequest("denominator", "EBITDA", current)),
            "multiple", current,
            lambda f: multiple(_ev(f), f["denominator"].value), None,
        ),
        "PE_RATIO": _MetricSpec(
            "CALC.PE_RATIO",
            "share_price / diluted_eps",
            (_InputRequest("price", "SHARE_PRICE", none, True), _InputRequest("denominator", "DILUTED_EPS", current, True)),
            "multiple", current,
            lambda f: multiple(f["price"].value, f["denominator"].value), None,
        ),
        "NET_DEBT_EBITDA": _MetricSpec(
            "CALC.NET_DEBT_EBITDA",
            "(gross_debt - cash) / ebitda",
            (_InputRequest("debt", "GROSS_DEBT", current), _InputRequest("cash", "CASH", current), _InputRequest("denominator", "EBITDA", current)),
            "multiple", current,
            lambda f: multiple(net_debt(f["debt"].value, f["cash"].value), f["denominator"].value), None,
        ),
    }


_EXPECTED_UNITS: Final[dict[str, str]] = {
    "REVENUE": "million_currency",
    "EBITDA": "million_currency",
    "CASH": "million_currency",
    "GROSS_DEBT": "million_currency",
    "SHARE_PRICE": "currency_per_share",
    "SHARES_OUTSTANDING": "million_shares",
    "DILUTED_EPS": "currency_per_share",
}


class DeterministicCalculationEngine:
    """Calculate only sealed F3 formulas over F1 facts sourced through F2."""

    def __init__(self, provider: FinancialDataProvider) -> None:
        if not isinstance(provider, FinancialDataProvider):
            raise TypeError("provider must implement FinancialDataProvider.")
        self._provider = provider
        self._specs = _specs()

    @property
    def supported_metrics(self) -> tuple[str, ...]:
        return SUPPORTED_METRICS

    def _result(
        self,
        *,
        company_id: str,
        security_id: str,
        metric_code: str,
        financial_period_id: str | None,
        as_of: datetime,
        spec: _MetricSpec,
        status: AnalyticalStatus,
        value: Decimal | None,
        currency: str | None,
        unit: str | None,
        input_fact_ids: tuple[str, ...],
        note: str | None,
    ) -> CalculationResult:
        provisional = CalculationResult(
            schema_version=CALCULATION_RESULT_SCHEMA_VERSION,
            workspace_id=self._provider.workspace.workspace_id,
            company_id=company_id,
            security_id=security_id,
            metric_code=metric_code,
            classification=ValueClassification.DERIVED_METRIC,
            calculation_classification=CalculationClassification.MODEL_CALCULATION,
            status=status,
            value=value,
            currency=currency,
            unit=unit,
            financial_period_id=financial_period_id,
            as_of=as_of,
            calculation_code=spec.calculation_code,
            calculation_version=CALCULATION_VERSION,
            formula=spec.formula,
            input_fact_ids=tuple(sorted(input_fact_ids)),
            note=note,
            result_id="sha256:" + "0" * 64,
        )
        result_id = derive_finance_id(calculation_result_identity_payload_to_dict(provisional))
        result = CalculationResult(
            schema_version=provisional.schema_version,
            workspace_id=provisional.workspace_id,
            company_id=provisional.company_id,
            security_id=provisional.security_id,
            metric_code=provisional.metric_code,
            classification=provisional.classification,
            calculation_classification=provisional.calculation_classification,
            status=provisional.status,
            value=provisional.value,
            currency=provisional.currency,
            unit=provisional.unit,
            financial_period_id=provisional.financial_period_id,
            as_of=provisional.as_of,
            calculation_code=provisional.calculation_code,
            calculation_version=provisional.calculation_version,
            formula=provisional.formula,
            input_fact_ids=provisional.input_fact_ids,
            note=provisional.note,
            result_id=result_id,
        )
        validate_calculation_result(result)
        return result

    def calculate(
        self,
        *,
        company_id: str,
        security_id: str,
        metric_code: str,
        current_period_id: str,
        prior_period_id: str,
        as_of: datetime,
    ) -> CalculationResult:
        spec = self._specs.get(metric_code)
        if spec is None:
            raise ValueError(f"Unsupported derived metric {metric_code!r}.")

        company = self._provider.get_company(company_id=company_id)
        if company is None:
            raise ValueError("company_id is outside provider authority.")
        security = self._provider.get_security(security_id=security_id)
        if security is None or security.company_id != company_id:
            raise ValueError("security_id is outside requested company authority.")

        periods = {item.financial_period_id: item for item in self._provider.list_periods(company_id=company_id)}
        current_period = periods.get(current_period_id)
        prior_period = periods.get(prior_period_id)
        if current_period is None:
            raise ValueError("current_period_id is outside requested company authority.")
        if prior_period is None:
            raise ValueError("prior_period_id is outside requested company authority.")
        if current_period_id == prior_period_id or current_period.end_date <= prior_period.end_date:
            raise ValueError("current/prior period ordering is not valid for deterministic comps calculations.")

        facts: dict[str, FinancialFact] = {}
        all_observation_ids: list[str] = []
        failures: list[tuple[str, FactResolution]] = []

        for request in spec.requests:
            period_id = (
                current_period_id if request.period == "current"
                else prior_period_id if request.period == "prior"
                else None
            )
            resolution = resolve_financial_fact(
                self._provider,
                company_id=company_id,
                metric_code=request.metric_code,
                as_of=as_of,
                security_id=security_id if request.security_bound else None,
                financial_period_id=period_id,
            )
            all_observation_ids.extend(resolution.observation_ids)
            if resolution.status is not AnalyticalStatus.ESTABLISHED:
                failures.append((request.metric_code, resolution))
            else:
                assert resolution.fact is not None
                facts[request.name] = resolution.fact

        if failures:
            status = (
                AnalyticalStatus.SOURCE_CONFLICT
                if any(item.status is AnalyticalStatus.SOURCE_CONFLICT for _, item in failures)
                else AnalyticalStatus.INSUFFICIENT_DATA
            )
            note = "; ".join(f"{metric}: {item.note}" for metric, item in failures)
            return self._result(
                company_id=company_id, security_id=security_id, metric_code=metric_code,
                financial_period_id=current_period_id if spec.output_period == "current" else None,
                as_of=as_of, spec=spec, status=status, value=None, currency=None, unit=None,
                input_fact_ids=tuple(f.fact_id for f in facts.values()), note=note,
            )

        # Fail closed on unsupported units rather than converting silently.
        for fact in facts.values():
            expected_unit = _EXPECTED_UNITS.get(fact.metric_code)
            if expected_unit is not None and fact.unit != expected_unit:
                return self._result(
                    company_id=company_id, security_id=security_id, metric_code=metric_code,
                    financial_period_id=current_period_id if spec.output_period == "current" else None,
                    as_of=as_of, spec=spec, status=AnalyticalStatus.ASSUMPTION_REQUIRED,
                    value=None, currency=None, unit=None,
                    input_fact_ids=tuple(f.fact_id for f in facts.values()),
                    note=f"Unsupported unit for {fact.metric_code}: {fact.unit}.",
                )

        monetary_currencies = {
            f.currency for f in facts.values()
            if f.metric_code in {"REVENUE", "EBITDA", "CASH", "GROSS_DEBT", "SHARE_PRICE", "DILUTED_EPS"}
        }
        if None in monetary_currencies or len(monetary_currencies) > 1:
            return self._result(
                company_id=company_id, security_id=security_id, metric_code=metric_code,
                financial_period_id=current_period_id if spec.output_period == "current" else None,
                as_of=as_of, spec=spec, status=AnalyticalStatus.ASSUMPTION_REQUIRED,
                value=None, currency=None, unit=None,
                input_fact_ids=tuple(f.fact_id for f in facts.values()),
                note="Currency normalisation or FX assumption would be required.",
            )

        try:
            value = spec.evaluator(facts)
        except ZeroDivisionError as exc:
            return self._result(
                company_id=company_id, security_id=security_id, metric_code=metric_code,
                financial_period_id=current_period_id if spec.output_period == "current" else None,
                as_of=as_of, spec=spec, status=AnalyticalStatus.NOT_ESTABLISHED,
                value=None, currency=None, unit=None,
                input_fact_ids=tuple(f.fact_id for f in facts.values()), note=str(exc),
            )

        currency = facts[spec.currency_source].currency if spec.currency_source is not None else None
        return self._result(
            company_id=company_id,
            security_id=security_id,
            metric_code=metric_code,
            financial_period_id=current_period_id if spec.output_period == "current" else None,
            as_of=as_of,
            spec=spec,
            status=AnalyticalStatus.ESTABLISHED,
            value=value,
            currency=currency,
            unit=spec.output_unit,
            input_fact_ids=tuple(f.fact_id for f in facts.values()),
            note=None,
        )

    def calculate_comps_metrics(
        self,
        *,
        company_id: str,
        security_id: str,
        current_period_id: str,
        prior_period_id: str,
        as_of: datetime,
    ) -> tuple[CalculationResult, ...]:
        return tuple(
            self.calculate(
                company_id=company_id,
                security_id=security_id,
                metric_code=metric_code,
                current_period_id=current_period_id,
                prior_period_id=prior_period_id,
                as_of=as_of,
            )
            for metric_code in SUPPORTED_METRICS
        )


__all__ = ["DeterministicCalculationEngine", "SUPPORTED_METRICS"]
