from dotenv import load_dotenv
load_dotenv()

import streamlit as st

st.set_page_config(
    page_title="Twilio API Explorer",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={},
)
st.markdown("<style>[data-testid='stSidebarNav'] {display: none;}</style>", unsafe_allow_html=True)

# Sidebar — credentials
with st.sidebar:
    st.markdown(
        "<h1 style='color:#F22F46; font-size:1.6rem; font-weight:800; letter-spacing:2px;'>TWILIO</h1>"
        "<p style='color:#888; margin-top:-10px; font-size:0.8rem;'>API Explorer</p>",
        unsafe_allow_html=True,
    )
    st.divider()

    import os
    st.session_state["account_sid"] = os.getenv("TWILIO_ACCOUNT_SID", "")
    st.session_state["auth_token"] = os.getenv("TWILIO_AUTH_TOKEN", "")

    st.divider()

    page = st.radio(
        "Navigation",
        options=["Channels", "Conversations", "Flex SDK", "Actions"],
        label_visibility="collapsed",
    )

# Two-column layout: main content (left) + request inspector (right)
main_col, inspector_col = st.columns([3, 1])

with main_col:
    if page == "Channels":
        from pages import channels
        channels.render()
    elif page == "Conversations":
        from pages import conversations
        conversations.render()
    elif page == "Flex SDK":
        from pages import flex_sdk
        flex_sdk.render()
    elif page == "Actions":
        from pages import actions
        actions.render()

with inspector_col:
    from pages.inspector import render_inspector
    render_inspector()
