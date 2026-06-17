import streamlit as st


def record_request(method: str, url: str, params: dict = None, body: dict = None, auth: tuple = None):
    st.session_state["last_request"] = {
        "method": method,
        "url": url,
        "params": params or {},
        "body": body or {},
        "auth": auth,
    }


def render_inspector():
    st.markdown(
        "<h4 style='color:#F22F46; font-size:0.95rem; letter-spacing:1px;'>REQUEST INSPECTOR</h4>",
        unsafe_allow_html=True,
    )
    st.divider()

    req = st.session_state.get("last_request")
    if not req:
        st.caption("No request made yet.")
        return

    method = req["method"]
    color = "#28a745" if method == "GET" else "#fd7e14" if method == "POST" else "#007bff"
    st.markdown(
        f"<span style='background:{color};color:white;padding:2px 8px;border-radius:4px;"
        f"font-size:0.75rem;font-weight:700;'>{method}</span>",
        unsafe_allow_html=True,
    )

    st.markdown("**URL**")
    st.code(req["url"], language=None)

    if req["params"]:
        st.markdown("**Query Params**")
        st.json(req["params"])

    if req["body"]:
        st.markdown("**Request Body**")
        st.json(req["body"])

    if req.get("auth"):
        account_sid, auth_token = req["auth"]
        st.markdown("**Auth (Basic)**")
        st.json({"account_sid": account_sid, "auth_token": auth_token[:4] + "****"})

    # Build full URL with query string for easy copy
    if req["params"]:
        from urllib.parse import urlencode
        full = req["url"] + "?" + urlencode(req["params"])
        st.markdown("**Full URL**")
        st.code(full, language=None)
