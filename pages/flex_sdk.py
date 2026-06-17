import streamlit as st
import requests
import os
from pages.inspector import record_request


def render():
    account_sid = st.session_state.get("account_sid", "")
    auth_token = st.session_state.get("auth_token", "")

    if not account_sid or not auth_token:
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    tab_fetch, tab_delete = st.tabs(["Fetch Task", "Delete Task"])

    with tab_fetch:
        st.markdown(
            "<h2 style='color:#F22F46;'>Fetch Task</h2>",
            unsafe_allow_html=True,
        )
        st.caption("Fetch Tasks")

        workspace_sid = workspace_sid = os.getenv("FLEX_APP_WORKSPACE_SID", "")
        task_sid = st.text_input("Task SID", placeholder="WT00ee58740ac143daa95adf3ed44db9c3")

        if st.button("Fetch", type="primary"):
            if not task_sid:
                st.error("Task SID is required.")
            else:
                url = f"https://taskrouter.twilio.com/v1/Workspaces/{workspace_sid}/Tasks/{task_sid}"
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
                        with st.expander("Full response"):
                            st.json(data)

                        st.markdown("---")

    with tab_delete:
        st.markdown(
            "<h2 style='color:#F22F46;'>Delete Task </h2>",
            unsafe_allow_html=True,
        )
        st.caption("Delete a Task by its SID.")

        workspace_sid = "WS37231a3da5824da58229cd7760041bce"
        delete_task_sid = st.text_input("Task SID", placeholder="WT00ee58740ac143daa95adf3ed44db9c3", key="delete_task_sid")

        if st.button("Delete Task", type="primary"):
            if not delete_task_sid:
                st.error("Task SID is required.")
            else:
                url = f"https://taskrouter.twilio.com/v1/Workspaces/{workspace_sid}/Tasks/{delete_task_sid}"
                record_request("DELETE", url, auth=(account_sid, auth_token))

                with st.spinner("Deleting task..."):
                    try:
                        resp = requests.delete(url, auth=(account_sid, auth_token), timeout=10)
                    except requests.RequestException as e:
                        st.error(f"Request failed: {e}")
                        resp = None

                if resp is not None:
                    if resp.status_code == 204:
                        st.success("Task deleted successfully.")
                    else:
                        st.error(f"Status {resp.status_code}: {resp.text}")
