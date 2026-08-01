import streamlit as st

from ui.header import show_header
from ui.sidebar import show_sidebar
from ui.chat import show_chat

st.set_page_config(

    page_title="LegalRAG Pro",

    page_icon="⚖️",

    layout="wide",

    initial_sidebar_state="expanded"
)

show_header()

selected_documents = show_sidebar()

show_chat(selected_documents)