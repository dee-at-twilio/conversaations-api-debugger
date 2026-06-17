import streamlit as st
import requests
from pages.inspector import record_request

# Base url: https://conversations.twilio.com (base url)
# POST https://conversations.twilio.com/v1/Conversations
# GET https://conversations.twilio.com/v1/Conversations/{Sid}
#     "webhooks": "https://conversations.twilio.com/v1/Conversations/CHaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/Webhooks",






def render():
    account_sid = st.session_state.get("account_sid", "")
    auth_token = st.session_state.get("auth_token", "")

    if not account_sid or not auth_token:
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    tab_webhooks, tab_delete = st.tabs(["List Channel", "Delete Channel"])

    with tab_webhooks:
        st.markdown(
            "<h2 style='color:#F22F46;'>List Channel</h2>",
            unsafe_allow_html=True,
        )
        st.caption("Fetch all webhooks configured for a Conversations channel.")

        # service_sid = st.text_input("Service SID", placeholder="IS37231a3da5824da58229cd7760041bce")
        channel_sid = st.text_input("Channel SID", placeholder="CH00ee58740ac143daa95adf3ed44db9c3")

        if st.button("Fetch", type="primary"):
            if not channel_sid:
                st.error("Channel SID is required.")
            else:
                url = f"https://conversations.twilio.com/v1/Conversations/{channel_sid}"
                record_request("GET", url, auth=(account_sid, auth_token))

                with st.spinner("Fetching..."):
                    try:
                        resp = requests.get(url, auth=(account_sid, auth_token), timeout=10)
                    except requests.RequestException as e:
                        st.error(f"Request failed: {e}")
                        resp = None

                if resp is not None:
                    if resp.status_code != 200:
                        st.error(f"Status {resp.status_code}: {resp.text}")
                    else:
                        data = resp.json()
                        webhooks = data.get("webhooks", None)
                        if webhooks is None:
                            webhooks = [data] if data.get("sid") else []

                        if not webhooks:
                            st.info("No data found for this channel.")
                        else:
                            for wh in webhooks:
                                filters = wh.get("configuration", {}).get("filters", [])
                                if filters:
                                    st.markdown("**Webhooks**")
                                    for f in filters:
                                        st.markdown(f"- `{f}`")
                        with st.expander("Full response"):
                            st.json(data)

                        st.markdown("---")

                        for label, endpoint in [
                            ("Messages", "Messages"),
                            ("Participants", "Participants"),
                            ("Webhooks", "Webhooks"),
                        ]:
                            sub_url = f"https://conversations.twilio.com/v1/Conversations/{channel_sid}/{endpoint}"
                            try:
                                sub_resp = requests.get(sub_url, auth=(account_sid, auth_token), timeout=10)
                            except requests.RequestException as e:
                                with st.expander(label):
                                    st.error(f"Request failed: {e}")
                                continue

                            with st.expander(f"{label} (Return status: {sub_resp.status_code})"):
                                if sub_resp.status_code == 200:
                                    st.json(sub_resp.json())
                                else:
                                    st.error(f"Status {sub_resp.status_code}: {sub_resp.text}")

    with tab_delete:
        st.markdown(
            "<h2 style='color:#F22F46;'>Delete Channel</h2>",
            unsafe_allow_html=True,
        )
        st.caption("Delete a Conversations channel by its SID.")

        service_sid = "IS37231a3da5824da58229cd7760041bce"
        delete_channel_sid = st.text_input("Channel SID", placeholder="CH39c3b60dd5704290ac790b01ebb5e9f8", key="delete_channel_sid")

        if st.button("Delete Channel", type="primary"):
            if not delete_channel_sid:
                st.error("Channel SID is required.")
            else:
                url = f"https://chat.twilio.com/v2/Services/{service_sid}/Channels/{delete_channel_sid}"
                record_request("DELETE", url, auth=(account_sid, auth_token))

                with st.spinner("Deleting channel..."):
                    try:
                        resp = requests.delete(url, auth=(account_sid, auth_token), timeout=10)
                    except requests.RequestException as e:
                        st.error(f"Request failed: {e}")
                        resp = None

                if resp is not None:
                    if resp.status_code == 204:
                        st.success("Channel deleted successfully.")
                    else:
                        st.error(f"Status {resp.status_code}: {resp.text}")
