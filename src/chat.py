import streamlit as st

from legalrag import ask


def _show_chat_api_busy_overlay():
    placeholder = st.empty()
    placeholder.markdown(
        """<style>
        .legalrag-chat-api-busy-overlay {
            position: fixed;
            inset: 0;
            z-index: 2147483000;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(107, 114, 128, 0.46);
            backdrop-filter: grayscale(45%) blur(1px);
            -webkit-backdrop-filter: grayscale(45%) blur(1px);
            pointer-events: all;
            cursor: wait;
        }
        .legalrag-chat-api-busy-card {
            max-width: 34rem;
            margin: 1rem;
            padding: 1.15rem 1.35rem;
            border-radius: 0.75rem;
            background: rgba(255, 255, 255, 0.97);
            box-shadow: 0 12px 36px rgba(0, 0, 0, 0.24);
            text-align: center;
            color: #1f2937;
        }
        .legalrag-chat-api-busy-spinner {
            width: 1.8rem;
            height: 1.8rem;
            margin: 0 auto 0.8rem auto;
            border: 0.2rem solid #d1d5db;
            border-top-color: #4b5563;
            border-radius: 50%;
            animation: legalrag-chat-api-spin 0.8s linear infinite;
        }
        @keyframes legalrag-chat-api-spin {
            to { transform: rotate(360deg); }
        }
        </style>
        <div class="legalrag-chat-api-busy-overlay" role="status"
             aria-live="polite" aria-busy="true">
            <div class="legalrag-chat-api-busy-card">
                <div class="legalrag-chat-api-busy-spinner"></div>
                <strong>AI request in progress</strong><br>
                <span>
                    Waiting for the API response.
                    The current governed authority is not being changed.
                </span>
            </div>
        </div>""",
        unsafe_allow_html=True,
    )
    return placeholder

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

            _chat_api_busy = _show_chat_api_busy_overlay()
            try:
                result = ask(
                    question,
                    selected_documents
                )
            finally:
                _chat_api_busy.empty()

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
