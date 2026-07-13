import streamlit as st
import requests
import pandas as pd
from collections import defaultdict
from datetime import datetime, timedelta, timezone


SUMMARIES_URL = "https://insights.twilio.com/v1/Voice/Summaries"
EVENTS_URL = "https://insights.twilio.com/v1/Voice/Calls/{call_sid}/Events"


def _auth():
    return (st.session_state.get("account_sid", ""), st.session_state.get("auth_token", ""))


def _fetch_summaries(start_dt: datetime, end_dt: datetime) -> list:
    """Fetch outbound_api call summaries (TAC-initiated calls) for the date range."""
    calls = []
    params = {
        "startTime": start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "direction": "outbound_api",
        "pageSize": 1000,
    }
    url = SUMMARIES_URL
    while url:
        resp = requests.get(url, auth=_auth(), params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        calls.extend(data.get("call_summaries", []))
        next_url = data.get("meta", {}).get("next_page_url")
        url = next_url if next_url else None
        params = {}  # next_page_url already has all params embedded
    return calls


def _fetch_cr_events(call_sid: str) -> list:
    """Fetch ConversationRelay events for a single call."""
    resp = requests.get(
        EVENTS_URL.format(call_sid=call_sid),
        auth=_auth(),
        timeout=10,
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("events", [])


def _is_cr_call(events: list) -> bool:
    cr_event_types = {
        "first_token_received", "final_token_received", "stt_latency",
        "tts_latency", "prompt_sent", "configurations",
    }
    return any(e.get("name") in cr_event_types for e in events)


def _metric_card(title: str, value: str, subtitle: str):
    st.markdown(
        f"""
        <div style="border:1px solid #e0e0e0;border-radius:10px;padding:16px 20px;min-height:100px;">
            <div style="font-size:0.8rem;color:#555;font-weight:500;">{title}</div>
            <div style="font-size:2rem;font-weight:700;margin:4px 0;">{value}</div>
            <div style="font-size:0.75rem;color:#888;">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _build_daily_df(calls: list) -> pd.DataFrame:
    daily: dict = defaultdict(list)
    for c in calls:
        raw = c.get("start_time", "") or ""
        if raw:
            daily[raw[:10]].append(c)

    rows = []
    for day in sorted(daily):
        day_calls = daily[day]
        rows.append({
            "date": day,
            "unique_contacts": len(set(c.get("to", {}).get("phone_number", "") for c in day_calls)),
            "total_calls": len(day_calls),
            "completed_calls": sum(1 for c in day_calls if c.get("call_state") == "completed"),
        })

    if not rows:
        return pd.DataFrame(columns=["date", "unique_contacts", "total_calls", "completed_calls"])
    return pd.DataFrame(rows)


def render():
    st.markdown(
        "<h2 style='color:#F22F46;'>AI Agent Insights</h2>",
        unsafe_allow_html=True,
    )
    st.caption("Monitor your AI outbound call agent's performance and call analytics")

    if not st.session_state.get("account_sid") or not st.session_state.get("auth_token"):
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    # ── Controls ─────────────────────────────────────────────────────────────
    col_range, _, col_refresh = st.columns([2, 4, 1])
    with col_range:
        date_range = st.selectbox(
            "Date range",
            options=["Last 7 days", "Last 30 days", "Last 90 days"],
            index=1,
            label_visibility="collapsed",
        )
    with col_refresh:
        refresh = st.button("Refresh", type="secondary")

    days = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}[date_range]
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)

    # ── Fetch call summaries (cached) ─────────────────────────────────────────
    cache_key = f"cr_insights_{date_range}"
    if refresh or cache_key not in st.session_state:
        with st.spinner("Fetching call summaries from Voice Insights..."):
            try:
                st.session_state[cache_key] = _fetch_summaries(start_dt, end_dt)
            except requests.HTTPError as e:
                st.error(f"Voice Insights API error {e.response.status_code}: {e.response.text}")
                return
            except Exception as e:
                st.error(f"Failed to fetch calls: {e}")
                return

    calls: list = st.session_state.get(cache_key, [])

    if not calls:
        st.info("No outbound API calls found for this date range.")
        return

    # ── Summary metrics ───────────────────────────────────────────────────────
    # to/from are objects: {"phone_number": "+1...", "carrier": ...}
    unique_contacts = len(set(
        (c.get("to") or {}).get("phone_number", "") for c in calls
    ) - {""})
    total_calls = len(calls)
    durations = [c.get("duration") or 0 for c in calls]
    avg_duration_sec = sum(durations) / len(durations) if durations else 0
    completed_calls = sum(1 for c in calls if c.get("call_state") == "completed")
    total_minutes = sum(durations) / 60
    time_saved_hours = total_minutes / 60

    # ── Metric cards: row 1 ───────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _metric_card("Total Unique Contacts", str(unique_contacts), "Individual customers called")
    with c2:
        _metric_card("Total Outbound Calls", str(total_calls), "Calls made by AI agent")
    with c3:
        _metric_card("Average Call Time", f"{avg_duration_sec / 60:.1f} min", "Average duration per call")
    with c4:
        _metric_card("Completed Calls", str(completed_calls), "Calls completed by AI agent")

    st.write("")

    # ── Metric cards: row 2 ───────────────────────────────────────────────────
    c5, c6 = st.columns(2)
    with c5:
        _metric_card("Total Call Minutes", f"{total_minutes:.0f}", "Total minutes of AI conversation")
    with c6:
        _metric_card("Time Saved", f"{time_saved_hours:.1f} hours", "Staff time saved through automation")

    st.write("")
    st.divider()

    # ── Charts ────────────────────────────────────────────────────────────────
    df = _build_daily_df(calls)

    chart_l, chart_r = st.columns(2)

    with chart_l:
        st.markdown("**Unique Contacts Over Time**")
        st.caption("Daily unique contacts reached by your AI agent")
        if not df.empty:
            st.line_chart(df.set_index("date")[["unique_contacts"]], use_container_width=True)

    with chart_r:
        st.markdown("**Call Volume & Outcomes**")
        st.caption("Daily outbound calls vs completed calls")
        if not df.empty:
            st.bar_chart(
                df.set_index("date")[["total_calls", "completed_calls"]],
                use_container_width=True,
                color=["#1f77b4", "#2ca02c"],
            )

    st.divider()

    # ── ConversationRelay events for a single call ────────────────────────────
    st.markdown("**ConversationRelay Event Inspector**")
    st.caption("Select a call to inspect its CR events (latency, ASR/TTS, turns)")

    call_options = {
        f"{(c.get('start_time') or '')[:19]}  —  {c.get('call_sid', '')}  →  {(c.get('to') or {}).get('phone_number', '?')}": c.get("call_sid")
        for c in sorted(calls, key=lambda x: x.get("start_time") or "", reverse=True)
    }
    selected_label = st.selectbox("Call", options=list(call_options.keys()), label_visibility="collapsed")
    selected_sid = call_options.get(selected_label)

    if selected_sid and st.button("Load CR Events", type="primary"):
        with st.spinner(f"Fetching events for {selected_sid}..."):
            events = _fetch_cr_events(selected_sid)

        if not events:
            st.info("No events found for this call. It may not have used ConversationRelay.")
        else:
            cr_types = {
                "first_token_received", "final_token_received", "stt_latency",
                "tts_latency", "prompt_sent", "interrupt", "configurations",
                "start_of_customer_speech", "end_of_customer_speech",
                "start_of_agent_speech", "end_of_agent_speech", "call_wrap_up",
            }
            cr_events = [e for e in events if e.get("name") in cr_types]

            if not cr_events:
                st.info("Call has events but none are ConversationRelay events.")
                with st.expander("All events"):
                    st.json(events)
            else:
                st.success(f"Found {len(cr_events)} ConversationRelay events")

                # Latency summary
                stt_latencies = [
                    e.get("event_data", {}).get("latency_ms") or e.get("latency_ms")
                    for e in cr_events if e.get("name") == "stt_latency"
                ]
                tts_latencies = [
                    e.get("event_data", {}).get("latency_ms") or e.get("latency_ms")
                    for e in cr_events if e.get("name") == "tts_latency"
                ]
                stt_latencies = [v for v in stt_latencies if v is not None]
                tts_latencies = [v for v in tts_latencies if v is not None]

                if stt_latencies or tts_latencies:
                    lc1, lc2 = st.columns(2)
                    with lc1:
                        avg_stt = sum(stt_latencies) / len(stt_latencies) if stt_latencies else 0
                        _metric_card("Avg STT Latency", f"{avg_stt:.0f} ms", "Speech-to-text processing time")
                    with lc2:
                        avg_tts = sum(tts_latencies) / len(tts_latencies) if tts_latencies else 0
                        _metric_card("Avg TTS Latency", f"{avg_tts:.0f} ms", "Text-to-speech processing time")
                    st.write("")

                event_rows = [
                    {
                        "sequence": e.get("sequence_number", ""),
                        "name": e.get("name", ""),
                        "timestamp": (e.get("timestamp") or "")[:19],
                        "data": str(e.get("event_data") or ""),
                    }
                    for e in sorted(cr_events, key=lambda x: x.get("sequence_number") or 0)
                ]
                st.dataframe(event_rows, use_container_width=True)

                with st.expander("Raw event payload"):
                    st.json(cr_events)

    st.divider()

    # ── Raw call table ────────────────────────────────────────────────────────
    with st.expander(f"All call records ({total_calls})"):
        rows = [
            {
                "Call SID": c.get("call_sid", ""),
                "To": (c.get("to") or {}).get("phone_number", ""),
                "From": (c.get("from_") or c.get("from") or {}).get("phone_number", ""),
                "State": c.get("call_state", ""),
                "Direction": c.get("direction", ""),
                "Duration (s)": c.get("duration") or 0,
                "Start Time": (c.get("start_time") or "")[:19],
            }
            for c in calls
        ]
        st.dataframe(rows, use_container_width=True)
