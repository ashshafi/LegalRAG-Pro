"""Pure non-UI activation service for the Finance runtime composition boundary."""

from __future__ import annotations

from finance_comps import ComparableSetDefinition
from finance_reporting import FinanceReportProjection
from finance_runtime import build_finance_runtime_projection
from finance_runtime_config import FinanceRuntimeConfig


def activate_finance_runtime(
    *,
    config: FinanceRuntimeConfig,
    definition: ComparableSetDefinition,
    documents,
    entries,
) -> FinanceReportProjection:
    """Build one Finance projection from explicit config and explicit runtime inputs."""

    if not isinstance(config, FinanceRuntimeConfig):
        raise TypeError("config must be a FinanceRuntimeConfig.")

    return build_finance_runtime_projection(
        definition=definition,
        documents=documents,
        entries=entries,
        **config.to_runtime_kwargs(),
    )


__all__ = ["activate_finance_runtime"]
