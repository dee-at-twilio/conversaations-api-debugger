import streamlit as st
import requests
from pages.inspector import record_request

BASE_URL = "https://conversations.twilio.com/v2/Conversations"


def _auth():
    return (st.session_state.get("account_sid", ""), st.session_state.get("auth_token", ""))


def render():
    st.markdown(
        "<h2 style='color:#F22F46;'>Conversations</h2>",
        unsafe_allow_html=True,
    )

    if not st.session_state.get("account_sid") or not st.session_state.get("auth_token"):
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    tab_list, tab_fetch, tab_update, tab_actions, tab_comms = st.tabs(
        ["List Conversations", "Fetch Conversation", "Update Conversation", "List Conversation Actions", "List Communications"]
    )

    # ── Tab 1: List ──────────────────────────────────────────────────────────
    with tab_list:
        st.subheader("List Conversations")
        col1, col2 = st.columns(2)
        with col1:
            status_filter = st.selectbox(
                "Status filter", options=["All", "ACTIVE", "INACTIVE", "CLOSED"]
            )
        with col2:
            page_size = st.number_input("Page size", min_value=1, max_value=100, value=20)

        if st.button("Fetch Conversations", type="primary", key="btn_list"):
            params = {"limit": page_size}
            if status_filter != "All":
                params["status"] = status_filter

            record_request("GET", BASE_URL, params=params, auth=_auth())
            with st.spinner("Fetching conversations..."):
                try:
                    resp = requests.get(BASE_URL, auth=_auth(), params=params, timeout=10)
                except requests.RequestException as e:
                    st.error(f"Request failed: {e}")
                    resp = None

            if resp is not None:
                if resp.status_code != 200:
                    st.error(f"Error {resp.status_code}: {resp.text}")
                else:
                    data = resp.json()
                    conversations = data.get("conversations", [])
                    if not conversations:
                        st.info("No conversations found.")
                    else:
                        st.success(f"Found {len(conversations)} conversation(s)")
                        for c in conversations:
                            label = c.get("name") or c.get("id", "Unknown")
                            col1, col2, col3, col4 = st.columns([3, 2, 1, 2])
                            col1.caption("ID"); col1.write(c.get("id", "—"))
                            col2.caption("Name"); col2.write(c.get("name") or "—")
                            col3.caption("Status"); col3.write(c.get("status", "—"))
                            col4.caption("Created"); col4.write((c.get("createdAt") or "—")[:10])
                            with st.expander(f"Full response — {label}"):
                                st.json(c)
                            st.divider()

    # ── Tab 2: Fetch ─────────────────────────────────────────────────────────
    with tab_fetch:
        st.subheader("Fetch a Conversation")
        sid = st.text_input(
            "Conversation SID", placeholder="conv_conversation_xxxxxxxxxxxxxxxxxxxxxxx", key="fetch_sid"
        )

        if st.button("Fetch", type="primary", key="btn_fetch"):
            if not sid:
                st.error("Conversation SID is required.")
            else:
                record_request("GET", f"{BASE_URL}/{sid}", auth=_auth())
                with st.spinner("Fetching conversation..."):
                    try:
                        resp = requests.get(f"{BASE_URL}/{sid}", auth=_auth(), timeout=10)
                    except requests.RequestException as e:
                        st.error(f"Request failed: {e}")
                        resp = None

                if resp is not None:
                    if resp.status_code != 200:
                        st.error(f"Error {resp.status_code}: {resp.text}")
                    else:
                        c = resp.json()
                        cfg = c.get("configuration", {})
                        fields = {
                            "Account ID": c.get("accountId", "—"),
                            "Status": c.get("status", "—"),
                            "Name": c.get("name") or "—",
                            "Created": (c.get("createdAt") or "—")[:10],
                            "Updated": (c.get("updatedAt") or "—")[:10],
                            "Grouping Type": cfg.get("conversationGroupingType", "—"),
                            "Bridge Service ID": (cfg.get("conversationsV1Bridge") or {}).get("serviceId", "—"),
                        }
                        items_html = "".join(
                            f"<div style='margin:4px 8px 4px 0;display:inline-block;'>"
                            f"<span style='font-size:0.7rem;color:#888;text-transform:uppercase;'>{k}</span><br>"
                            f"<span style='font-size:0.85rem;font-weight:600;'>{v}</span></div>"
                            for k, v in fields.items()
                        )
                        st.markdown(
                            f"<div style='display:flex;flex-wrap:wrap;gap:4px;'>{items_html}</div>",
                            unsafe_allow_html=True,
                        )

                        participants = c.get("participants", [])
                        if participants:
                            st.markdown("**Participants**")
                            for p in participants:
                                addresses = p.get("addresses", [])
                                addr_str = ", ".join(
                                    f"{a.get('address', '—')} ({a.get('channelId', '—')})"
                                    for a in addresses
                                ) or "—"
                                st.markdown(
                                    f"- **{p.get('type', '—')}** — {p.get('name', '—')} - {p.get('profileId', '—')} &nbsp; `{addr_str}`",
                                    unsafe_allow_html=True,
                                )

                        with st.expander("Full response"):
                            st.json(c)

    # ── Tab 3: Update ─────────────────────────────────────────────────────────
    with tab_update:
        st.subheader("Update a Conversation")
        upd_sid = st.text_input(
            "Conversation SID", placeholder="conv_conversation_xxxxxxxxxxxxxxxxxxxxxxx", key="update_sid"
        )
        new_state = st.selectbox("State (required)", options=["ACTIVE", "INACTIVE", "CLOSED"])
        # new_name = st.text_input("Friendly Name (optional)", placeholder="Leave blank to keep existing")

        if st.button("Update Conversation", type="primary", key="btn_update"):
            if not upd_sid:
                st.error("Conversation SID is required.")
            else:
                body = {"status": new_state}

                record_request("PUT", f"{BASE_URL}/{upd_sid}", body=body, auth=_auth())
                with st.spinner("Updating conversation..."):
                    try:
                        resp = requests.put(
                            f"{BASE_URL}/{upd_sid}", auth=_auth(), json=body, timeout=10
                        )
                    except requests.RequestException as e:
                        st.error(f"Request failed: {e}")
                        resp = None

                if resp is not None:
                    if resp.status_code not in (200, 204):
                        st.error(f"Code {resp.status_code}: {resp.text}")
                    else:
                        st.success("Conversation updated successfully.")
                        if resp.content:
                            with st.expander("Updated conversation"):
                                st.json(resp.json())

    # ── Tab 4: List Actions ─────────────────────────────────────────────────────────
    with tab_actions:
        st.subheader("List Conversation actions")
        col1, col2 = st.columns(2)
        with col1:
            status_filter = st.selectbox(
                "Status filter", options=["All", "active", "inactive", "closed"], key="actions_status_filter"
            )
        with col2:
            page_size = st.number_input("Page size", min_value=1, max_value=100, value=20, key="actions_page_size")

        if st.button("Fetch Conversations", type="primary", key="btn_actions_list"):
            params = {"PageSize": page_size}
            if status_filter != "All":
                params["State"] = status_filter

            record_request("GET", f"{BASE_URL}?status=ACTIVE&status=INACTIVE&status=CLOSED", params=params, auth=_auth())
            with st.spinner("Fetching conversations..."):
                try:
                    resp = requests.get(f"{BASE_URL}?status=ACTIVE&status=INACTIVE&status=CLOSED", auth=_auth(), params=params, timeout=10)
                except requests.RequestException as e:
                    st.error(f"Request failed: {e}")
                    resp = None

            if resp is not None:
                if resp.status_code != 200:
                    st.error(f"Error {resp.status_code}: {resp.text}")
                else:
                    data = resp.json()
                    conversations = data.get("conversations", [])
                    if not conversations:
                        st.info("No conversations found.")
                    else:
                        st.success(f"Found {len(conversations)} conversation(s)")
                        rows = [
                            {
                                "sid": c.get("sid", ""),
                                "friendly_name": c.get("friendly_name") or "",
                                "state": c.get("state", ""),
                                "date_created": c.get("date_created", ""),
                            }
                            for c in conversations
                        ]
                        st.dataframe(rows, use_container_width=True)
                        for c in conversations:
                            label = c.get("friendly_name") or c.get("sid", "Unknown")
                            with st.expander(f"📄 {c.get('sid', '')} — {label}"):
                                st.json(c)

    # ── Tab 5: List Communications ─────────────────────────────────────────────
    with tab_comms:
        st.subheader("List Communications by Conversation")
        comms_sid = st.text_input(
            "Conversation SID",
            placeholder="conv_conversation_xxxxxxxxxxxxxxxxxxxxxxx",
            key="comms_sid",
        )
        col1, col2 = st.columns(2)
        with col1:
            channel_id = st.text_input("Channel ID (optional)", key="comms_channel_id")
        with col2:
            comms_page_size = st.number_input(
                "Page size", min_value=1, max_value=1000, value=50, key="comms_page_size"
            )

        if st.button("Fetch Communications", type="primary", key="btn_comms_list"):
            if not comms_sid:
                st.error("Conversation SID is required.")
            else:
                url = f"{BASE_URL}/{comms_sid}/Communications"
                params = {"pageSize": comms_page_size}
                if channel_id:
                    params["channelId"] = channel_id

                record_request("GET", url, params=params, auth=_auth())
                with st.spinner("Fetching communications..."):
                    try:
                        resp = requests.get(url, auth=_auth(), params=params, timeout=10)
                    except requests.RequestException as e:
                        st.error(f"Request failed: {e}")
                        resp = None

                if resp is not None:
                    if resp.status_code != 200:
                        st.error(f"Error {resp.status_code}: {resp.text}")
                    else:
                        data = resp.json()
                        communications = data.get("communications", [])
                        if not communications:
                            st.info("No communications found.")
                        else:
                            st.success(f"Found {len(communications)} communication(s)")
                            for comm in communications:
                                author = comm.get("author") or {}
                                content = comm.get("content") or {}
                                recipients = comm.get("recipients") or []
                                col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
                                col1.caption("ID"); col1.write(comm.get("id", "—"))
                                col2.caption("Channel"); col2.write(author.get("channel", "—"))
                                col3.caption("From"); col3.write(author.get("address", "—"))
                                col4.caption("Occurred"); col4.write((comm.get("occurredAt") or "—")[:19])

                                if content.get("type") == "TEXT" and content.get("text"):
                                    st.markdown(f"> {content['text']}")
                                else:
                                    st.markdown(f"*{content.get('type', '—')}*")

                                if recipients:
                                    to_str = ", ".join(
                                        f"{r.get('address', '—')} ({r.get('deliveryStatus', '—')})"
                                        for r in recipients
                                    )
                                    st.caption(f"To: {to_str}")

                                with st.expander(f"Full response — {comm.get('id', '')}"):
                                    st.json(comm)
                                st.divider()

