from pathlib import Path

import streamlit as st


def show_sidebar():
    """
    Display the application sidebar.

    Returns
    -------
    tuple
        (
            selected_documents,
            timeline_clicked
        )
    """

    st.sidebar.title("📚 Documents")

    docs = sorted(
        Path("docs").glob("*.pdf")
    )

    selected_documents = []

    for pdf in docs:

        if st.sidebar.checkbox(
            pdf.name,
            value=True
        ):
            selected_documents.append(
                pdf.name
            )

    st.sidebar.divider()

    st.sidebar.title("⚖ Tribunal Tools")

    timeline_clicked = st.sidebar.button(
        "📅 Timeline",
        use_container_width=True
    )

    st.sidebar.button(
        "📚 Evidence Explorer",
        use_container_width=True
    )

    st.sidebar.button(
        "👤 People Explorer",
        use_container_width=True
    )

    st.sidebar.button(
        "📑 Compare Documents",
        use_container_width=True
    )

    st.sidebar.button(
        "📄 Reports",
        use_container_width=True
    )

    st.sidebar.divider()

    st.sidebar.title("📊 Status")

    st.sidebar.success(
        "OpenAI Connected"
    )

    st.sidebar.success(
        "Chroma Connected"
    )

    st.sidebar.info(
        f"{len(docs)} document(s) indexed"
    )

    return (
        selected_documents,
        timeline_clicked
    )