"""LegalRAG Pro D4 commercial visual system."""

from __future__ import annotations
import streamlit as st

_CSS = r"""
<style>
:root{
 --ink:#172033;--text:#2b3850;--muted:#667085;--subtle:#98a2b3;
 --line:#e2e8f0;--line2:#cfd8e3;--bg:#f6f8fb;--panel:#fff;
 --navy:#173b67;--navy2:#102f50;--green:#067647;--greenbg:#ecfdf3;
 --greenline:#abefc6;--amber:#93370d;--amberbg:#fffaeb;--amberline:#fedf89;
 --red:#b42318;--redbg:#fef3f2;--redline:#fecdca;
}
html,body,[class*="css"]{font-family:Inter,"Segoe UI",Roboto,Arial,sans-serif;color:var(--text)}
.stApp,[data-testid="stAppViewContainer"]{background:var(--bg)}
header[data-testid="stHeader"]{background:transparent}
#MainMenu,footer{visibility:hidden}
.block-container{max-width:1320px;padding:.8rem 2rem 4rem 2rem}

/* restrained product bar */
.lr-appbar{min-height:46px;display:flex;align-items:center;justify-content:space-between;
 gap:16px;padding:2px 0 10px;border-bottom:1px solid var(--line);margin-bottom:14px}
.lr-brand{display:flex;align-items:center;gap:9px}
.lr-brand-mark{width:27px;height:27px;display:flex;align-items:center;justify-content:center;
 border-radius:6px;background:var(--navy);color:white;font-size:10px;font-weight:800}
.lr-brand-name{font-size:15.5px;font-weight:760;letter-spacing:-.02em;color:var(--ink)}
.lr-brand-meta,.lr-appbar-right{font-size:10.5px;color:var(--muted);margin-top:1px}

/* matter identity */
.lr-matter-head{padding:1px 0 8px}
.lr-eyebrow{font-size:9.5px;text-transform:uppercase;letter-spacing:.1em;font-weight:760;color:var(--muted)}
.lr-matter-title{font-size:23px;line-height:1.2;font-weight:760;letter-spacing:-.035em;color:var(--ink);margin-top:2px}
.lr-matter-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:5px;font-size:11.5px;color:var(--muted)}
.lr-status{display:inline-flex;align-items:center;padding:2px 7px;border-radius:999px;border:1px solid var(--greenline);
 background:var(--greenbg);color:var(--green);font-size:9.5px;font-weight:720}

/* utility sidebar, not product navigation */
section[data-testid="stSidebar"]{width:220px!important;min-width:220px!important;background:#fff!important;border-right:1px solid var(--line)!important}
section[data-testid="stSidebar"]>div:first-child{padding-top:.65rem!important}
section[data-testid="stSidebar"] .block-container{padding-left:.75rem!important;padding-right:.75rem!important}
section[data-testid="stSidebar"] h1{font-size:16px!important;margin:.4rem 0 .55rem!important}
section[data-testid="stSidebar"] h2,section[data-testid="stSidebar"] h3{font-size:13px!important}
section[data-testid="stSidebar"] [data-testid="stExpander"]{border:0!important;background:transparent!important}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary{font-size:11.5px!important;padding:.15rem 0!important}
section[data-testid="stSidebar"] .stButton>button{background:transparent!important;border-color:transparent!important;
 justify-content:flex-start!important;min-height:31px!important;font-size:11.5px!important;padding:.3rem .4rem!important}
section[data-testid="stSidebar"] .stButton>button:hover{background:#f5f7fa!important;border-color:#edf1f5!important}
.lr-side-heading{font-size:15px;font-weight:730;color:var(--ink);letter-spacing:-.02em;margin:.5rem 0 .6rem}

/* controls */
.stButton>button,.stFormSubmitButton>button,.stDownloadButton>button{border-radius:6px!important;min-height:35px;
 padding:.4rem .7rem!important;font-size:12px!important;font-weight:630!important;box-shadow:none!important;white-space:nowrap!important}
button[kind="primary"]{background:var(--navy)!important;border:1px solid var(--navy)!important;color:#fff!important}
button[kind="primary"]:hover{background:var(--navy2)!important;border-color:var(--navy2)!important}
button[kind="secondary"]{background:#fff!important;border:1px solid var(--line2)!important;color:var(--text)!important}
button[kind="secondary"]:hover{background:#f8fafc!important;border-color:#aeb9c8!important}

/* true segmented navigation */
[data-testid="stSegmentedControl"]{margin:.1rem 0 .75rem!important}
[data-testid="stSegmentedControl"]>div{background:#edf1f6!important;border:1px solid var(--line)!important;border-radius:7px!important;padding:3px!important}
[data-testid="stSegmentedControl"] button{border:0!important;border-radius:5px!important;min-height:31px!important;
 padding:.28rem .62rem!important;font-size:11.5px!important;font-weight:620!important;box-shadow:none!important}

/* standard typography */
h1,h2,h3,h4{color:var(--ink)!important;font-family:inherit!important;letter-spacing:-.025em!important}
h1{font-size:26px!important;line-height:1.18!important;font-weight:740!important;margin:1rem 0 .6rem!important}
h2{font-size:19px!important;font-weight:700!important;margin:1.05rem 0 .45rem!important}
h3{font-size:15.5px!important;font-weight:690!important;margin:.9rem 0 .35rem!important}
p,li,[data-testid="stMarkdownContainer"]{line-height:1.5}
[data-testid="stCaptionContainer"]{font-size:11px!important;color:var(--muted)!important}

/* inputs and data */
[data-baseweb="select"]>div,[data-testid="stTextInput"] input,[data-testid="stTextArea"] textarea{
 background:#fff!important;border:1px solid var(--line2)!important;border-radius:6px!important;box-shadow:none!important}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 13px;box-shadow:0 1px 2px rgba(16,24,40,.03)}
[data-testid="stMetricLabel"]{font-size:10.5px!important;color:var(--muted)!important;font-weight:620!important}
[data-testid="stMetricValue"]{font-size:22px!important;color:var(--ink)!important;font-weight:720!important;letter-spacing:-.03em!important}
[data-testid="stExpander"],[data-testid="stVerticalBlockBorderWrapper"]{background:#fff!important;border:1px solid var(--line)!important;border-radius:7px!important;box-shadow:none!important}
[data-testid="stAlert"]{border-radius:7px!important;box-shadow:none!important}
hr{border-color:var(--line)!important;margin:.9rem 0!important}
[data-testid="stDataFrame"],[data-testid="stTable"]{border:1px solid var(--line)!important;border-radius:7px!important;overflow:hidden!important;background:#fff!important}

/* overview dashboard */
.lr-page-heading{margin:.55rem 0 .1rem;color:var(--ink);font-size:26px;line-height:1.18;font-weight:745;letter-spacing:-.035em}
.lr-page-lede{font-size:11.5px;color:var(--muted);margin-bottom:.9rem}
.lr-section-title{font-size:15.5px;font-weight:700;color:var(--ink);letter-spacing:-.018em;margin:1rem 0 .55rem}
.lr-attention-list{display:grid;gap:7px;margin-bottom:.9rem}
.lr-attention-card{display:grid;grid-template-columns:32px minmax(0,1fr);gap:10px;padding:12px 13px;background:#fff;border:1px solid var(--line);border-radius:8px}
.lr-attention-index{width:27px;height:27px;display:flex;align-items:center;justify-content:center;background:#eef3f9;color:var(--navy);border-radius:6px;font-size:10px;font-weight:760}
.lr-attention-title{font-size:13.5px;font-weight:690;color:var(--ink);margin-bottom:5px}
.lr-chiprow{display:flex;gap:5px;flex-wrap:wrap;margin-bottom:5px}
.lr-chip{display:inline-flex;padding:2px 6px;border:1px solid var(--line);border-radius:999px;background:#f8fafc;color:#475467;font-size:9px;font-weight:720;letter-spacing:.035em;text-transform:uppercase}
.lr-chip--high{color:var(--amber);background:var(--amberbg);border-color:var(--amberline)}
.lr-chip--overdue{color:var(--red);background:var(--redbg);border-color:var(--redline)}
.lr-workline{font-size:12px;line-height:1.45;color:var(--text);padding-top:2px}
.lr-summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:.3rem 0 .85rem}
.lr-summary-card{padding:11px 12px;background:#fff;border:1px solid var(--line);border-radius:8px;min-height:76px}
.lr-summary-label{font-size:9px;color:var(--muted);font-weight:730;letter-spacing:.06em;text-transform:uppercase;margin-bottom:5px}
.lr-summary-value{font-size:12.5px;line-height:1.42;color:var(--ink);font-weight:620}

/* reports */
.lr-report-title{font-size:26px;line-height:1.18;font-weight:745;letter-spacing:-.035em;color:var(--ink);margin:.55rem 0 .12rem}
.lr-report-subtitle{font-size:11.5px;color:var(--muted);margin-bottom:.85rem}
.lr-report-intro{background:#fff;border:1px solid var(--line);border-radius:8px;padding:12px 13px;margin:.3rem 0 .75rem}
.lr-report-intro-title{font-size:13px;font-weight:690;color:var(--ink);margin-bottom:3px}
.lr-report-intro-copy{font-size:11.2px;line-height:1.45;color:var(--muted)}
.lr-audit-note{padding:8px 10px;border-left:3px solid #9db4cf;background:#f5f8fc;color:#526174;font-size:11px;line-height:1.45;margin:.5rem 0}

@media(max-width:1000px){
 section[data-testid="stSidebar"]{width:200px!important;min-width:200px!important}
 .block-container{padding-left:1.15rem;padding-right:1.15rem}
 .lr-summary-grid{grid-template-columns:1fr}
}
</style>
"""

def apply_product_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

__all__ = ["apply_product_theme"]
