import streamlit as st

from legalrag import ask


def show_chat(selected_documents):

    st.header("💬 AI Assistant")

    question = st.text_input(
        "Ask a legal question"
    )

    if st.button("🔍 Ask"):

        if not question:

            st.warning(
                "Please enter a question."
            )

            return

        with st.spinner(
            "Searching evidence..."
        ):

            result = ask(
                question,
                selected_documents
            )

        st.subheader("📄 Answer")

        st.write(result["answer"])

        st.divider()

        st.subheader("📚 Evidence")

        for source in result["sources"]:

            st.write(
                f"📄 {source['file']} — Page {source['page']}"
            )