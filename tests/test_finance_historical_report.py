from __future__ import annotations

import os
from pathlib import Path

from finance_data.immutable_dataset import loads_immutable_dataset_document, validate_immutable_dataset_document
from finance_historical_report import (
    build_historical_finance_report,
    render_historical_finance_html,
    render_historical_finance_markdown,
)


def _dataset():
    path = Path(os.environ["LEGALRAG_CACI_DATASET"])
    document = loads_immutable_dataset_document(path.read_text(encoding="utf-8"))
    return validate_immutable_dataset_document(
        document,
        expected_provider_id="caci-accounts-pdf",
        expected_dataset_id="CACI-01649776-HISTORICAL-2004-2006",
        expected_dataset_version="1",
    )


def test_real_caci_historical_report_is_direct_deterministic_and_source_bound():
    dataset = _dataset()
    report1 = build_historical_finance_report(dataset=dataset)
    report2 = build_historical_finance_report(dataset=dataset)
    assert report1 == report2
    assert report1.report_id == report2.report_id
    assert len(report1.period_ids) == 3
    assert len(report1.metric_codes) == 9
    assert len(report1.values) == 27
    assert all(row.security_id is None for row in report1.values)
    assert "EBITDA" not in report1.metric_codes
    assert {row.observation_id for row in report1.values} == {row.observation_id for row in dataset.observations}
    assert {row.source_id for row in report1.values} == {row.source_id for row in dataset.observations}
    md1 = render_historical_finance_markdown(report1)
    md2 = render_historical_finance_markdown(report2)
    html1 = render_historical_finance_html(report1)
    html2 = render_historical_finance_html(report2)
    assert md1 == md2
    assert html1 == html2
    assert "Historical Finance Report" in md1
    assert "<!doctype html>" in html1
    assert "Comparable" not in md1
    assert "Peer" not in md1
    assert "EBITDA" not in md1
