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
            "Searching documents..."
        ):

            result = ask(
                question,
                selected_documents
            )

        # ----------------------------
        # Answer
        # ----------------------------

        st.subheader("📄 Answer")

        st.success(result["answer"])

        st.divider()

        # ----------------------------
        # Evidence
        # ----------------------------

        st.subheader("📚 Supporting Evidence")

        if not result["sources"]:

            st.info("No supporting evidence found.")

            return

        for source in result["sources"]:

            preview = source["text"][:250]

            if len(source["text"]) > 250:
                preview += "..."

            st.markdown(
                f"### 📄 {source['file']}"
            )

            st.caption(
                f"Page {source['page']}"
            )

            st.write(preview)

            with st.expander(
                "Show full evidence"
            ):

                st.write(source["text"])

            st.divider()