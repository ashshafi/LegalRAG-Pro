from pathlib import Path

import streamlit as st

from document_manager import get_documents
from index_documents import index_pdf


def show_sidebar():

    selected_documents = []

    with st.sidebar:

        st.header("📚 Documents")

        documents = get_documents()

        st.caption(
            f"{len(documents)} document(s) indexed"
        )

        st.divider()

        search = st.text_input(
            "🔍 Search documents"
        )

        for document in documents:

            if search.lower() in document.lower():

                if st.checkbox(
                    document,
                    value=True
                ):
                    selected_documents.append(
                        document
                    )

        st.divider()

        uploaded_file = st.file_uploader(
            "Upload PDF",
            type=["pdf"]
        )

        if uploaded_file:

            docs_folder = Path("docs")
            docs_folder.mkdir(exist_ok=True)

            save_path = docs_folder / uploaded_file.name

            with open(save_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            st.success("PDF saved")

            if st.button("📥 Index Document"):

                with st.spinner(
                    "Indexing..."
                ):
                    index_pdf(save_path)

                st.success(
                    "Finished indexing"
                )

        st.divider()

        st.subheader("⚖ Tribunal Tools")

        st.button("📅 Timeline")

        st.button("📚 Evidence Explorer")

        st.button("👤 People Explorer")

        st.button("📑 Compare Documents")

        st.button("📄 Reports")

    return selected_documents