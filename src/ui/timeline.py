import streamlit as st


def show_timeline(events):

    st.header("📅 Timeline")

    if not events:

        st.info("No timeline events found.")

        return

    for event in events:

        with st.expander(
            f"{event['date']} — {event['file']}"
        ):

            st.write(event["event"])

            st.caption(
                f"📄 {event['file']} | Page {event['page']}"
            )