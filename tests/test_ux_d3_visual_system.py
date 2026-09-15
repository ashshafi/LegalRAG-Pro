from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def source(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8-sig")


def test_d3_visual_modules_parse():
    for rel in (
        "src/ui/product_theme.py",
        "src/ui/header.py",
        "src/ui/solicitor_shell.py",
    ):
        ast.parse(source(rel), filename=rel)


def test_d3_removes_promotional_hero_and_broken_button_grid():
    header = source("src/ui/header.py")
    shell = source("src/ui/solicitor_shell.py")

    assert "background-color:#1E293B" not in header
    assert "lr-appbar" in header
    assert "st.segmented_control(" in shell
    assert "st.radio(" not in shell


def test_d3_theme_has_professional_product_primitives():
    theme = source("src/ui/product_theme.py")

    assert "LegalRAG Pro D4 commercial visual system" in theme
    assert "_CSS" in theme
    assert "apply_product_theme" in theme
    assert "unsafe_allow_html=True" in theme


def test_d3_app_applies_theme_before_product_header():
    app = source("src/app.py")
    assert "from ui.product_theme import apply_product_theme" in app
    assert app.index("apply_product_theme()") < app.index("show_header()")


def test_d3_overview_does_not_repeat_promotional_title():
    overview = source("src/ui/matter_overview.py")
    assert "⚖️ Matter Overview" not in overview
    assert "\\u2696\\ufe0f Matter Overview" not in overview
    assert 'st.title("Overview")' in overview


def test_d3_does_not_invent_a_legal_risk_label():
    overview = source("src/ui/matter_overview.py")
    assert "HIGH RISK" not in overview
