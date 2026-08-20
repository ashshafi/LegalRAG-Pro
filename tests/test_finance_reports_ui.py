import importlib
import sys
import types

from finance_reporting import render_finance_html_report, render_finance_markdown_report
from test_finance_reporting_models import projection


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = {}
        self.downloads = []

    def subheader(self, *args, **kwargs):
        pass

    def caption(self, *args, **kwargs):
        pass

    def download_button(self, label, **kwargs):
        self.downloads.append((label, kwargs))


def test_exports_are_exact_f7a_deterministic_renderers():
    fake = FakeStreamlit()
    sys.modules["streamlit"] = fake
    sys.modules.pop("ui.finance_reports", None)
    reports = importlib.import_module("ui.finance_reports")
    p = projection()
    reports.render_finance_report_exports(p)
    assert len(fake.downloads) == 2
    by_label = {label: kwargs for label, kwargs in fake.downloads}
    assert by_label["Download Markdown"]["data"] == render_finance_markdown_report(p)
    assert by_label["Download HTML"]["data"] == render_finance_html_report(p)
    assert by_label["Download Markdown"]["file_name"].endswith(".md")
    assert by_label["Download HTML"]["file_name"].endswith(".html")
