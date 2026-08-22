import streamlit as st


def show_header():

    st.markdown("""
    <div style="
        background-color:#1E293B;
        padding:20px;
        border-radius:12px;
        margin-bottom:20px;
    ">

    <h1 style="color:white;margin:0;">
    ⚖ LegalRAG Pro
    </h1>

    <p style="
        color:#CBD5E1;
        font-size:18px;
        margin-top:8px;
    ">
    Auditable Case Intelligence
    </p>

    </div>
    """,
    unsafe_allow_html=True
    )