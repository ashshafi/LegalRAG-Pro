import importlib
import sys
import types
from dataclasses import replace

from finance_reporting import build_finance_report_projection
from finance_workspace_index import build_finance_workspace_index
from test_finance_reporting_models import analysis, mixed_manifest_for, projection


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.calls = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            key = kwargs.get("key")
            if name in {"radio", "selectbox"}:
                options = args[1] if len(args) > 1 else ()
                if key and key not in self.session_state and options:
                    self.session_state[key] = options[0]
                return self.session_state.get(key, options[0] if options else None)
            if name == "multiselect":
                if key and key not in self.session_state:
                    self.session_state[key] = []
                return self.session_state.get(key, [])
            if name == "text_input":
                if key and key not in self.session_state:
                    self.session_state[key] = ""
                return self.session_state.get(key, "")
            return None
        return call


def load_workspace_module():
    fake = FakeStreamlit()
    sys.modules["streamlit"] = fake
    sys.modules.pop("ui.finance_reports", None)
    sys.modules.pop("ui.finance_workspace", None)
    reports = importlib.import_module("ui.finance_reports")
    workspace = importlib.import_module("ui.finance_workspace")
    return fake, workspace, reports


def test_session_state_binds_exact_four_part_identity_and_resets_transient_filters():
    fake, ui, _ = load_workspace_module()
    p = projection()
    assert ui.synchronise_finance_workspace_session_state(p.header.workspace_id, p) is True
    fake.session_state["finance_matrix_query"] = "EV_EBITDA"
    assert ui.synchronise_finance_workspace_session_state(p.header.workspace_id, p) is False
    assert fake.session_state["finance_matrix_query"] == "EV_EBITDA"

    changed = replace(p, report_projection_id="sha256:" + "1" * 64)
    # Validation must fail rather than accepting identity drift that is not internally coherent.
    try:
        ui.synchronise_finance_workspace_session_state(p.header.workspace_id, changed)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid altered projection should fail validation")

    assert fake.session_state["finance_report_projection_id"] == p.report_projection_id
    assert fake.session_state["finance_projection_payload_sha256"] == p.projection_payload_sha256
    assert fake.session_state["finance_report_manifest_id"] == p.manifest.manifest_id


def test_metric_matrix_rows_preserve_raw_values_statuses_and_literal_filters_only():
    _, ui, _ = load_workspace_module()
    p = projection()
    i = build_finance_workspace_index(p)
    rows = ui.metric_matrix_rows(i)
    assert tuple(r["cell_id"] for r in rows) == p.manifest.ordered_cell_ids
    by_id = {c.cell_id: c for c in p.cells}
    for row in rows:
        cell = by_id[row["cell_id"]]
        assert row["raw_status"] == cell.analytical_status.value
        assert row["value"] == (None if cell.value is None else str(cell.value))
        assert row["currency"] == cell.currency
        assert row["unit"] == cell.unit
        assert row["value_classification"] == cell.value_classification.value

    metric = p.cells[0].metric_code
    filtered = ui.metric_matrix_rows(i, metric_codes=(metric,))
    assert filtered and all(r["metric"] == metric for r in filtered)
    literal = ui.metric_matrix_rows(i, query=metric.casefold())
    assert literal and any(r["metric"] == metric for r in literal)
    assert ui.metric_matrix_rows(i, query="semantic alias that is absent") == ()


def test_evidence_rows_preserve_all_f5_binding_states_and_no_source_text_is_added():
    _, ui, _ = load_workspace_module()
    a = analysis()
    p = build_finance_report_projection(analysis=a, evidence_manifest=mixed_manifest_for(a))
    i = build_finance_workspace_index(p)
    rows = ui.evidence_register_rows(i)
    assert {r["source_channel"] for r in rows} >= {"DOCUMENT", "STRUCTURED_PROVIDER", "MARKET"}
    assert {r["binding_class"] for r in rows} >= {"DOCUMENT_TEXT_BOUND", "DOCUMENT_UNBOUND", "NOT_APPLICABLE"}
    bound = next(r for r in rows if r["binding_class"] == "DOCUMENT_TEXT_BOUND")
    assert bound["document_snapshot_id"] is not None
    assert bound["page_number"] is not None
    assert bound["bound_text_sha256"] is not None
    assert "source_text" not in bound


def test_render_workspace_consumes_index_and_uses_read_only_streamlit_surface():
    fake, ui, _ = load_workspace_module()
    p = projection()
    i = build_finance_workspace_index(p)
    ui.render_finance_workspace(p.header.workspace_id, p, i)
    names = [name for name, _, _ in fake.calls]
    assert "header" in names
    assert "radio" in names
    assert "text" in names or "caption" in names
    assert not any(name in {"form_submit_button", "file_uploader"} for name in names)
