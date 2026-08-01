import streamlit as st
from pathlib import Path


def show_sidebar():

    st.sidebar.title("📚 Documents")

    docs = sorted(
        Path("docs").glob("*.pdf")
    )

    selected = []

    for pdf in docs:

        if st.sidebar.checkbox(
            pdf.name,
            value=True
        ):
            selected.append(pdf.name)

    st.sidebar.divider()

    st.sidebar.title("⚖ Tribunal Tools")

    st.sidebar.button("📅 Timeline")

    st.sidebar.button("📚 Evidence Explorer")

    st.sidebar.button("👤 People Explorer")

    st.sidebar.button("📑 Compare Documents")

    st.sidebar.button("📄 Reports")

    st.sidebar.divider()

    st.sidebar.title("📊 Status")

    st.sidebar.success("OpenAI Connected")

    st.sidebar.success("Chroma Connected")

    st.sidebar.info(
        f"{len(docs)} document(s)"
    )

    return selected