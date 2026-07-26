import json

import requests
import streamlit as st


INTEL_BASE = "https://intelligence.twilio.com/v3"
MEMORY_BASE = "https://memory.twilio.com/v1"
CONVERSATIONS_BASE = "https://conversations.twilio.com/v2"


def _auth():
    return (st.session_state["account_sid"], st.session_state["auth_token"])


def _headers():
    return {"Content-Type": "application/json"}


def _show_error(prefix: str, resp: requests.Response) -> None:
    try:
        body = resp.json()
    except Exception:
        body = resp.text
    st.error(f"{prefix} — HTTP {resp.status_code}")
    with st.expander("Response body"):
        st.json(body) if isinstance(body, dict) else st.code(body)


def _parse_json_area(label: str, raw: str) -> tuple[bool, object]:
    raw = (raw or "").strip()
    if not raw:
        return True, None
    try:
        return True, json.loads(raw)
    except json.JSONDecodeError as e:
        st.error(f"{label}: invalid JSON — {e}")
        return False, None


def render():
    st.markdown(
        "<h2 style='color:#F22F46;'>Conversation Intelligence & Memory</h2>",
        unsafe_allow_html=True,
    )

    if not st.session_state.get("account_sid") or not st.session_state.get("auth_token"):
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    tab_op, tab_rule, tab_view, tab_update, tab_convs = st.tabs(
        [
            "Custom operator",
            "Attach to config",
            "View memory",
            "Update memory",
            "View profile conversations",
        ],
    )

    with tab_op:
        _tab_custom_operator()

    with tab_rule:
        _tab_attach_to_config()

    with tab_view:
        _tab_view_memory()

    with tab_update:
        _tab_update_memory()

    with tab_convs:
        _tab_view_profile_conversations()


# ---------------------------------------------------------------------------
# Tab 1: Custom operator
# ---------------------------------------------------------------------------

def _tab_custom_operator():
    st.subheader("Create a custom Language Operator")
    st.caption(
        "Defines a reusable analysis task run against captured conversations. "
        "The prompt is what the LLM sees at execution time."
    )

    display_name = st.text_input("Display name", key="op_display_name", placeholder="Escalation Risk Detector")
    output_format = st.selectbox(
        "Output format",
        options=["TEXT", "CLASSIFICATION", "JSON"],
        index=0,
        key="op_output_format",
        help="TEXT and CLASSIFICATION auto-generate a schema. JSON lets you define one.",
    )

    memory_enabled = st.checkbox(
        "Enable memory tools",
        value=False,
        key="op_memory_enabled",
        help=(
            "Exposes the observational memory search tool and the trait memory fetch tool to the operator. "
            "You still need to instruct the LLM to call them in the prompt below — e.g. "
            "'Use the trait memory fetch tool to retrieve the customer's VIP status.'"
        ),
    )

    prompt = st.text_area(
        "Prompt",
        key="op_prompt",
        height=280,
        placeholder=(
            "Analyze the conversation between the customer and agent.\n"
            "Use the trait memory fetch tool to retrieve the customer's tier and preferred channel.\n"
            "Use the observational memory search tool to find prior complaints.\n"
            "Classify escalation risk as LOW, MEDIUM, or HIGH."
        ),
        help="Use {{parameters.name}} to interpolate parameter values.",
    )

    with st.expander("Advanced (optional)"):
        description = st.text_input("Description", key="op_description")
        parameters_raw = st.text_area(
            "Parameters (JSON)",
            key="op_parameters",
            height=120,
            placeholder='{"productName": {"type": "STRING", "required": true, "description": "Product line"}}',
        )
        output_schema_raw = st.text_area(
            "Output schema (JSON — only used when output format is JSON)",
            key="op_output_schema",
            height=160,
            placeholder='{"type": "object", "properties": {"risk": {"type": "string"}}}',
            help="Twilio auto-sets additionalProperties:false and marks all fields required. Use "
                 '["string","null"] union types for nullable fields.',
        )
        training_examples_raw = st.text_area(
            "Training examples (JSON array of {input, output})",
            key="op_training_examples",
            height=140,
            placeholder='[{"input": "Customer is furious", "output": "HIGH"}]',
        )

    if st.button("Create operator", type="primary", key="btn_create_op"):
        missing = [k for k, v in {"Display name": display_name, "Prompt": prompt}.items() if not v]
        if missing:
            st.error(f"Required fields missing: {', '.join(missing)}")
            st.stop()

        ok, parameters = _parse_json_area("Parameters", parameters_raw)
        if not ok:
            st.stop()
        ok, output_schema = _parse_json_area("Output schema", output_schema_raw)
        if not ok:
            st.stop()
        ok, training_examples = _parse_json_area("Training examples", training_examples_raw)
        if not ok:
            st.stop()

        body = {
            "displayName": display_name,
            "prompt": prompt,
            "outputFormat": output_format,
        }
        if description:
            body["description"] = description
        if parameters is not None:
            body["parameters"] = parameters
        if output_format == "JSON" and output_schema is not None:
            body["outputSchema"] = output_schema
        if training_examples is not None:
            body["trainingExamples"] = training_examples
        if memory_enabled:
            body["context"] = {"memory": {"enabled": True}}

        with st.spinner("Creating operator..."):
            resp = requests.post(
                f"{INTEL_BASE}/ControlPlane/Operators",
                auth=_auth(),
                headers=_headers(),
                json=body,
            )
        if resp.status_code >= 300:
            _show_error("Failed to create operator", resp)
            st.stop()

        data = resp.json()
        operator_id = data.get("id")
        version = data.get("version")
        st.session_state["last_operator_id"] = operator_id
        st.success(f"Operator created: {operator_id} (version {version})")
        with st.expander("Full response"):
            st.json(data)

    st.divider()

    with st.expander("List existing custom operators"):
        if st.button("Refresh", key="btn_list_ops"):
            resp = requests.get(
                f"{INTEL_BASE}/ControlPlane/Operators",
                auth=_auth(),
                headers=_headers(),
                params={"pageSize": 50},
            )
            if resp.status_code >= 300:
                _show_error("Failed to list operators", resp)
            else:
                items = resp.json().get("items", [])
                custom = [o for o in items if o.get("author") == "SELF"]
                if not custom:
                    st.info("No custom operators found.")
                else:
                    for op in custom:
                        st.write(f"**{op.get('displayName')}** — `{op.get('id')}` (v{op.get('version')})")


# ---------------------------------------------------------------------------
# Tab 2: Attach operator to a config
# ---------------------------------------------------------------------------

def _tab_attach_to_config():
    st.subheader("Attach operator to Intelligence Configuration")
    st.caption(
        "Adds a rule that runs the operator on a trigger and posts results to your webhook. "
        "Because PUT creates an inactive version, this deletes and recreates the config with the merged rules."
    )

    config_id = st.text_input(
        "Intelligence Configuration ID",
        key="rule_config_id",
        placeholder="intelligence_configuration_...",
    )
    operator_id = st.text_input(
        "Operator ID",
        value=st.session_state.get("last_operator_id", ""),
        key="rule_operator_id",
        placeholder="intelligence_operator_...",
    )
    trigger_on = st.selectbox(
        "Trigger",
        options=["COMMUNICATION", "CONVERSATION_END", "CONVERSATION_INACTIVE"],
        key="rule_trigger",
    )
    throttle = st.number_input(
        "Throttle count (COMMUNICATION only, 1-20)",
        min_value=1,
        max_value=20,
        value=1,
        key="rule_throttle",
    )
    webhook_url = st.text_input("Webhook URL", key="rule_webhook", placeholder="https://your-app.com/ci-results")

    if st.button("Attach rule", type="primary", key="btn_attach"):
        missing = [
            k for k, v in {
                "Config ID": config_id,
                "Operator ID": operator_id,
                "Webhook URL": webhook_url,
            }.items() if not v
        ]
        if missing:
            st.error(f"Required fields missing: {', '.join(missing)}")
            st.stop()

        # 1. Fetch current config
        with st.spinner("Fetching current config..."):
            get_resp = requests.get(
                f"{INTEL_BASE}/ControlPlane/Configurations/{config_id}",
                auth=_auth(),
                headers=_headers(),
            )
        if get_resp.status_code >= 300:
            _show_error("Failed to fetch config", get_resp)
            st.stop()
        current = get_resp.json()

        # 2. Build new rule and merge
        trigger = {"on": trigger_on}
        if trigger_on == "COMMUNICATION" and throttle > 1:
            trigger["parameters"] = {"count": int(throttle)}
        new_rule = {
            "operators": [{"id": operator_id}],
            "triggers": [trigger],
            "actions": [{"type": "WEBHOOK", "method": "POST", "url": webhook_url}],
        }
        rules = current.get("rules", []) + [new_rule]

        # 3. DELETE + POST (per skill: PUT silently deactivates)
        with st.spinner("Deleting existing config..."):
            del_resp = requests.delete(
                f"{INTEL_BASE}/ControlPlane/Configurations/{config_id}",
                auth=_auth(),
                headers=_headers(),
            )
        if del_resp.status_code >= 300 and del_resp.status_code != 404:
            _show_error("Failed to delete config", del_resp)
            st.stop()

        with st.spinner("Recreating config with new rule..."):
            create_body = {
                "displayName": current.get("displayName", "Config"),
                "description": current.get("description"),
                "rules": [_strip_rule_ids(r) for r in rules],
            }
            create_resp = requests.post(
                f"{INTEL_BASE}/ControlPlane/Configurations",
                auth=_auth(),
                headers=_headers(),
                json={k: v for k, v in create_body.items() if v is not None},
            )
        if create_resp.status_code >= 300:
            _show_error("Failed to recreate config", create_resp)
            st.stop()

        new_config = create_resp.json()
        st.success(f"Rule attached. New config ID: {new_config.get('id')}")
        st.warning(
            "Config was recreated — update any external references (Conversation Orchestrator "
            "intelligenceConfigurationIds) to point at the new ID above."
        )
        with st.expander("Full response"):
            st.json(new_config)

    with st.expander("Sample webhook payload"):
        st.caption("Shape your handler expects — from Twilio's Rule Execution webhook docs.")
        st.json({
            "accountId": "ACxxxxxxxxxxxxxxxx",
            "conversationId": "conversation_...",
            "intelligenceConfigurationId": "intelligence_configuration_...",
            "operatorResults": [
                {
                    "operator": {"id": "intelligence_operator_...", "version": 1},
                    "outputFormat": "CLASSIFICATION",
                    "result": {"label": "HIGH"},
                    "executionDetails": {
                        "trigger": {"on": "COMMUNICATION"},
                        "resolvedContext": {
                            "memory": {"profileId": "mem_profile_...", "memoryStoreId": "mem_store_..."},
                            "knowledge": {"sources": []},
                        },
                    },
                    "metadata": {
                        "system": {
                            "resolvedModel": "gpt-4o-mini",
                            "latencyMs": 1234,
                            "inputCharacters": 5000,
                            "outputCharacters": 20,
                            "inputTruncated": False,
                        }
                    },
                }
            ],
        })
        st.info(
            "Public docs don't spell out retry/signature semantics — verify against the Rule Execution "
            "webhook reference before relying on this in production."
        )


def _strip_rule_ids(rule: dict) -> dict:
    """Rule IDs are server-generated; passing existing ones back on create is rejected."""
    return {k: v for k, v in rule.items() if k != "id"}


# ---------------------------------------------------------------------------
# Tab 3: View memory (current traits + Recall)
# ---------------------------------------------------------------------------

def _tab_view_memory():
    st.subheader("View profile traits & recall memories")

    stores = _list_stores()
    if stores is None:
        return
    if not stores:
        st.info("No memory stores found. Create one via the Memory API first.")
        return

    store_labels = {f"{s.get('displayName') or s.get('id')} — {s.get('id')}": s.get("id") for s in stores}
    picked = st.selectbox("Memory Store", options=list(store_labels.keys()), key="traits_store")
    store_id = store_labels[picked]
    st.session_state["traits_store_id"] = store_id

    lookup_mode = st.radio(
        "Find profile by",
        options=["Phone number", "Profile ID"],
        horizontal=True,
        key="traits_lookup_mode",
    )

    if lookup_mode == "Phone number":
        phone = st.text_input("Phone (E.164)", placeholder="+447876762080", key="traits_phone")
        if st.button("Look up profile", key="btn_traits_lookup"):
            with st.spinner("Looking up profile..."):
                lookup_resp = requests.post(
                    f"{MEMORY_BASE}/Stores/{store_id}/Profiles/Lookup",
                    auth=_auth(),
                    headers=_headers(),
                    json={"idType": "phone", "value": phone},
                )
            if lookup_resp.status_code >= 300:
                _show_error("Lookup failed", lookup_resp)
                st.stop()

            lookup_data = lookup_resp.json()
            profiles = lookup_data.get("profiles", [])
            if not profiles:
                st.warning(
                    f"No profile found for {lookup_data.get('normalizedValue', phone)}."
                )
                st.stop()

            found_id = profiles[0]
            st.session_state["traits_profile_id"] = found_id
            st.session_state.pop("current_traits", None)
            st.session_state.pop("recall_result", None)
            st.success(
                f"Found profile: {found_id} "
                f"(normalized: {lookup_data.get('normalizedValue', '?')})"
            )
            if len(profiles) > 1:
                st.info(f"{len(profiles)} profiles matched; showing the first. All: {profiles}")
    else:
        manual_id = st.text_input("Profile ID", key="traits_manual_id")
        if manual_id and manual_id != st.session_state.get("traits_profile_id"):
            st.session_state["traits_profile_id"] = manual_id
            st.session_state.pop("current_traits", None)
            st.session_state.pop("recall_result", None)

    profile_id = st.session_state.get("traits_profile_id")

    if not profile_id:
        return

    st.divider()

    if st.button("Refresh current traits", key="btn_traits_refresh"):
        st.session_state.pop("current_traits", None)

    if "current_traits" not in st.session_state:
        with st.spinner("Loading traits..."):
            resp = requests.get(
                f"{MEMORY_BASE}/Stores/{store_id}/Profiles/{profile_id}/Traits",
                auth=_auth(),
                headers=_headers(),
                params={"pageSize": 200},
            )
        if resp.status_code >= 300:
            _show_error("Failed to load traits", resp)
            st.session_state["current_traits"] = {"items": []}
        else:
            st.session_state["current_traits"] = resp.json()

    traits_data = st.session_state.get("current_traits", {"items": []})
    grouped: dict[str, dict] = {}
    for t in traits_data.get("items", []):
        grouped.setdefault(t.get("traitGroup", "default"), {})[t.get("name")] = t.get("value")

    st.markdown("**Current traits**")
    if not grouped:
        st.caption("(none)")
    else:
        st.json(grouped)

    st.divider()
    _recall_section(store_id, profile_id)


def _recall_section(store_id: str, profile_id: str) -> None:
    st.markdown("**Recall memories**")
    st.caption(
        "Runs `POST /v1/Stores/{storeId}/Profiles/{profileId}/Recall` — returns observations "
        "and summaries for the profile. Leave query and conversation ID blank for most-recent order."
    )

    recall_query = st.text_input(
        "Query (optional)",
        key="recall_query",
        placeholder="What has the customer complained about?",
    )
    recall_conv = st.text_input("Conversation ID (optional)", key="recall_conv")
    col1, col2, col3 = st.columns(3)
    with col1:
        obs_limit = st.slider("Observations limit", min_value=1, max_value=20, value=10, key="recall_obs_limit")
    with col2:
        summ_limit = st.slider("Summaries limit", min_value=0, max_value=10, value=5, key="recall_summ_limit")
    with col3:
        comm_limit = st.slider("Communications limit", min_value=0, max_value=10, value=5, key="recall_comm_limit")

    if st.button("Run Recall", type="primary", key="btn_recall"):
        body = {"observationsLimit": obs_limit, "summariesLimit": summ_limit, "communicationsLimit": comm_limit}
        if recall_query:
            body["query"] = recall_query
        if recall_conv:
            body["conversationId"] = recall_conv
        with st.spinner("Recalling..."):
            resp = requests.post(
                f"{MEMORY_BASE}/Stores/{store_id}/Profiles/{profile_id}/Recall",
                auth=_auth(),
                headers=_headers(),
                json=body,
            )
        if resp.status_code >= 300:
            _show_error("Recall failed", resp)
            st.stop()
        st.session_state["recall_result"] = resp.json()

    data = st.session_state.get("recall_result")
    if not data:
        return

    observations = data.get("observations", [])
    summaries = data.get("summaries", [])
    communications = data.get("communications", [])

    st.markdown(f"### Observations ({len(observations)})")
    if not observations:
        st.caption("(none)")
    for o in observations:
        _render_memory_card(
            content=o.get("content", ""),
            memory_id=o.get("id", ""),
            conversation_ids=o.get("conversationIds") or [],
            source=o.get("source", ""),
            score=o.get("score"),
            occurred_at=o.get("occurredAt", ""),
        )

    st.markdown(f"### Summaries ({len(summaries)})")
    if not summaries:
        st.caption("(none)")
    for s in summaries:
        conv_id = s.get("conversationId", "")
        _render_memory_card(
            content=s.get("content", ""),
            memory_id=s.get("id", ""),
            conversation_ids=[conv_id] if conv_id else [],
            source=s.get("source", ""),
            score=s.get("score"),
            occurred_at=s.get("occurredAt", ""),
        )

    st.markdown(f"### Communications ({len(communications)})")
    if not communications:
        st.caption("(none)")
    for c in communications:
        _render_communication_card(c)

    with st.expander("Raw response"):
        st.json(data)


def _list_stores():
    resp = requests.get(
        f"{MEMORY_BASE}/ControlPlane/Stores",
        auth=_auth(),
        headers=_headers(),
        params={"pageSize": 50},
    )
    if resp.status_code >= 300:
        _show_error("Failed to list memory stores", resp)
        return None
    stores = []
    for s in resp.json().get("stores", []):
        if isinstance(s, dict):
            stores.append(s)
            continue
        detail = requests.get(
            f"{MEMORY_BASE}/ControlPlane/Stores/{s}",
            auth=_auth(),
            headers=_headers(),
        )
        stores.append(detail.json() if detail.ok else {"id": s})
    return stores


# ---------------------------------------------------------------------------
# Tab 4: Update memory (update traits)
# ---------------------------------------------------------------------------

def _tab_update_memory():
    st.subheader("Update profile traits")

    store_id = st.session_state.get("traits_store_id")
    profile_id = st.session_state.get("traits_profile_id")

    if not store_id or not profile_id:
        st.info("Pick a Memory Store and look up a profile on the *View memory* tab first.")
        return

    st.caption(
        f"Profile: `{profile_id}` in store `{store_id}`. "
        "Change the target on the *View memory* tab."
    )

    st.markdown("**Update traits**")
    st.caption(
        "Merge-only — traits you don't include stay unchanged. "
        "PATCH `/v1/Stores/{storeId}/Profiles/{profileId}` with a `traits` object."
    )

    trait_group = st.text_input(
        "Trait group",
        value="Contact",
        key="traits_group",
        help="Common groups: Contact, Account, Support. Define your own for domain data.",
    )

    if "trait_rows" not in st.session_state:
        st.session_state["trait_rows"] = [{"key": "", "value": ""}]

    rows = st.session_state["trait_rows"]
    updated_rows = []
    for i, row in enumerate(rows):
        c1, c2, c3 = st.columns([3, 5, 1])
        with c1:
            k = st.text_input("Field", value=row["key"], key=f"trait_key_{i}", label_visibility="collapsed", placeholder="firstName")
        with c2:
            v = st.text_input("Value", value=row["value"], key=f"trait_val_{i}", label_visibility="collapsed", placeholder="Alyssa")
        with c3:
            keep = not st.button("×", key=f"trait_del_{i}")
        if keep:
            updated_rows.append({"key": k, "value": v})
    st.session_state["trait_rows"] = updated_rows

    if st.button("+ Add field", key="btn_add_trait_row"):
        st.session_state["trait_rows"].append({"key": "", "value": ""})
        st.rerun()

    if st.button("Update traits", type="primary", key="btn_traits_update"):
        traits_payload = {r["key"]: r["value"] for r in updated_rows if r["key"]}
        if not traits_payload:
            st.error("Add at least one field with a key.")
            st.stop()

        body = {"traits": {trait_group: traits_payload}}
        with st.spinner("Patching profile..."):
            resp = requests.patch(
                f"{MEMORY_BASE}/Stores/{store_id}/Profiles/{profile_id}",
                auth=_auth(),
                headers=_headers(),
                json=body,
            )
        if resp.status_code >= 300:
            _show_error("Failed to update traits", resp)
        else:
            st.success("Traits updated.")
            st.session_state.pop("current_traits", None)
            with st.expander("Response"):
                st.json(resp.json())


# ---------------------------------------------------------------------------
# Tab 5: View profile conversations
# ---------------------------------------------------------------------------

def _tab_view_profile_conversations():
    st.subheader("View all conversations for a profile")
    st.caption(
        "Uses Recall to discover conversation IDs on this profile, then lists each "
        "conversation's communications via `GET /v2/Conversations/{id}/Communications` "
        "and merges them sorted newest-first."
    )

    stores = _list_stores()
    if stores is None:
        return
    if not stores:
        st.info("No memory stores found. Create one via the Memory API first.")
        return

    store_labels = {f"{s.get('displayName') or s.get('id')} — {s.get('id')}": s.get("id") for s in stores}
    picked = st.selectbox("Memory Store", options=list(store_labels.keys()), key="conv_store")
    store_id = store_labels[picked]

    lookup_mode = st.radio(
        "Find profile by",
        options=["Phone number", "Profile ID"],
        horizontal=True,
        key="conv_lookup_mode",
    )

    if lookup_mode == "Phone number":
        phone = st.text_input("Phone (E.164)", placeholder="+447876762080", key="conv_phone")
        if st.button("Look up profile", key="btn_conv_lookup"):
            with st.spinner("Looking up profile..."):
                lookup_resp = requests.post(
                    f"{MEMORY_BASE}/Stores/{store_id}/Profiles/Lookup",
                    auth=_auth(),
                    headers=_headers(),
                    json={"idType": "phone", "value": phone},
                )
            if lookup_resp.status_code >= 300:
                _show_error("Lookup failed", lookup_resp)
                st.stop()

            lookup_data = lookup_resp.json()
            profiles = lookup_data.get("profiles", [])
            if not profiles:
                st.warning(f"No profile found for {lookup_data.get('normalizedValue', phone)}.")
                st.stop()

            found_id = profiles[0]
            st.session_state["conv_profile_id"] = found_id
            st.session_state.pop("conv_result", None)
            st.success(
                f"Found profile: {found_id} "
                f"(normalized: {lookup_data.get('normalizedValue', '?')})"
            )
            if len(profiles) > 1:
                st.info(f"{len(profiles)} profiles matched; showing the first. All: {profiles}")
    else:
        manual_id = st.text_input("Profile ID", key="conv_manual_id")
        if manual_id and manual_id != st.session_state.get("conv_profile_id"):
            st.session_state["conv_profile_id"] = manual_id
            st.session_state.pop("conv_result", None)

    profile_id = st.session_state.get("conv_profile_id")
    if not profile_id:
        return

    st.divider()

    st.caption(
        "Recall's communications don't carry a `conversationId`, so we scan observations & summaries "
        "to discover the conversations this profile has appeared in."
    )
    recall_limit = st.slider(
        "Recall items to scan (observations)",
        min_value=1,
        max_value=100,
        value=25,
        key="conv_recall_limit",
    )
    per_conv_limit = st.slider(
        "Max communications per conversation",
        min_value=1,
        max_value=100,
        value=10,
        key="conv_per_conv_limit",
    )

    if st.button("Load conversations", type="primary", key="btn_load_conv"):
        with st.spinner("Recalling profile memory..."):
            recall_resp = requests.post(
                f"{MEMORY_BASE}/Stores/{store_id}/Profiles/{profile_id}/Recall",
                auth=_auth(),
                headers=_headers(),
                json={
                    "observationsLimit": recall_limit,
                    # "summariesLimit": recall_limit,
                    "communicationsLimit": 0,
                },
            )
        if recall_resp.status_code >= 300:
            _show_error("Recall failed", recall_resp)
            st.stop()
        recall_data = recall_resp.json()

        conv_ids: set[str] = set()
        for o in recall_data.get("observations", []):
            for cid in (o.get("conversationIds") or []):
                if cid:
                    conv_ids.add(cid)
        # for s in recall_data.get("summaries", []):
        #     cid = s.get("conversationId")
        #     if cid:
        #         conv_ids.add(cid)

        if not conv_ids:
            st.warning("No conversation IDs found in recall results.")
            st.session_state["conv_result"] = {"comms": [], "conv_ids": [], "errors": []}
            st.stop()

        all_comms: list[dict] = []
        errors: list[tuple[str, int]] = []
        with st.spinner(f"Fetching communications for {len(conv_ids)} conversation(s)..."):
            for cid in conv_ids:
                r = requests.get(
                    f"{CONVERSATIONS_BASE}/Conversations/{cid}/Communications",
                    auth=_auth(),
                    headers=_headers(),
                    params={"pageSize": per_conv_limit},
                )
                if r.status_code >= 300:
                    errors.append((cid, r.status_code))
                    continue
                body = r.json()
                items = body.get("communications") or body.get("items") or []
                for item in items:
                    item.setdefault("conversationId", cid)
                    all_comms.append(item)

        all_comms.sort(key=lambda c: c.get("createdAt") or "", reverse=True)

        st.session_state["conv_result"] = {
            "comms": all_comms,
            "conv_ids": sorted(conv_ids),
            "errors": errors,
        }

    result = st.session_state.get("conv_result")
    if not result:
        return

    conv_ids_loaded = result["conv_ids"]
    all_comms = result["comms"]
    errors = result["errors"]

    st.markdown(
        f"### {len(all_comms)} communication(s) across {len(conv_ids_loaded)} conversation(s)"
    )
    if conv_ids_loaded:
        with st.expander("Conversations discovered"):
            for cid in conv_ids_loaded:
                st.write(f"`{cid}`")
    for cid, status in errors:
        st.warning(f"Conversation `{cid}` — failed to fetch (HTTP {status})")

    if not all_comms:
        st.caption("(no communications returned)")
        return

    for comm in all_comms:
        _render_communication_card(comm)


def _render_memory_card(
    content: str,
    memory_id: str,
    conversation_ids: list[str],
    source: str,
    score,
    occurred_at: str,
) -> None:
    """Render one observation/summary with the identifying IDs the user asked for."""
    with st.container(border=True):
        st.write(content)
        conv_display = ", ".join(f"`{c}`" for c in conversation_ids) if conversation_ids else "—"
        score_display = f"{score:.3f}" if isinstance(score, (int, float)) else "—"
        st.caption(
            f"**Memory ID:** `{memory_id}`  \n"
            f"**Conversation ID:** {conv_display}  \n"
            f"**Intelligence source:** `{source or '—'}`  \n"
            f"**Occurred at:** {occurred_at or '—'} · **Score:** {score_display}"
        )


def _participant_label(p: dict, include_delivery: bool = False) -> str:
    if not isinstance(p, dict):
        return "—"
    name = p.get("name") or p.get("address") or p.get("id") or "—"
    ptype = p.get("type")
    label = f"{name} ({ptype})" if ptype else name
    if include_delivery and p.get("deliveryStatus"):
        label += f" · {p['deliveryStatus']}"
    return label


def _render_communication_card(comm: dict) -> None:
    text = (comm.get("content") or {}).get("text", "")
    author = comm.get("author") or {}
    recipients = comm.get("recipients") or []
    author_display = _participant_label(author)
    recipients_display = (
        ", ".join(_participant_label(r, include_delivery=True) for r in recipients)
        if recipients else "—"
    )
    channel = author.get("channel") or "—"
    conv_id = comm.get("conversationId")
    with st.container(border=True):
        st.write(text or "_(no text content)_")
        lines = [
            f"**Communication ID:** `{comm.get('id', '—')}`",
            f"**Channel ID:** `{comm.get('channelId', '—')}` · **Channel:** `{channel}`",
            f"**From:** {author_display}",
            f"**To:** {recipients_display}",
            f"**Created:** {comm.get('createdAt', '—')}",
        ]
        if conv_id:
            lines.insert(1, f"**Conversation ID:** `{conv_id}`")
        st.caption("  \n".join(lines))
