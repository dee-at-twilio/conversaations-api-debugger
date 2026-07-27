import os
import time
import uuid

import requests
import streamlit as st
from twilio.twiml.voice_response import Connect, ConversationRelay, VoiceResponse

from pages.inspector import record_request


ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "lcMyyd2HUfFzxdCaC4Ta")

GREETINGS = {
    "en-US": "Hello, this is your AI assistant. How can I help you today?",
    "es-US": "Hola, soy su asistente de inteligencia artificial. ¿Cómo puedo ayudarle hoy?",
    "fr-FR": "Bonjour, je suis votre assistant IA. Comment puis-je vous aider aujourd'hui ?",
    "de-DE": "Hallo, ich bin Ihr KI-Assistent. Wie kann ich Ihnen heute helfen?",
    "pt-BR": "Olá, sou seu assistente de IA. Como posso ajudá-lo hoje?",
    "hi-IN": "नमस्ते, मैं आपका एआई सहायक हूँ। मैं आज आपकी कैसे मदद कर सकता हूँ?",
}

CR_EVENT_NAMES = {
    "prompt_sent",
    "first_token_received",
    "final_token_received",
    "start_of_customer_speech",
    "end_of_customer_speech",
    "start_of_agent_speech",
    "end_of_agent_speech",
}


def _build_twiml(ws_url: str, greeting: str, extra_params: dict | None = None) -> str:
    vr = VoiceResponse()
    connect = Connect()
    cr = ConversationRelay(
        url=ws_url,
        welcome_greeting=greeting,
        language="multi",
        transcription_language="multi",
        tts_language="multi",
        tts_provider="ElevenLabs",
        voice=ELEVENLABS_VOICE_ID,
        transcription_provider="Deepgram",
        speech_model="nova-3-general",
    )
    for name, value in (extra_params or {}).items():
        cr.parameter(name=name, value=value)
    connect.append(cr)
    vr.append(connect)
    return str(vr)


def _place_call(sid: str, token: str, to: str, from_: str, twiml: str) -> requests.Response:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    body = {"To": to, "From": from_, "Twiml": twiml}
    record_request("POST", url, body=body, auth=(sid, token))
    return requests.post(url, auth=(sid, token), data=body, timeout=15)


def _fetch_cr_events(sid: str, token: str, call_sid: str) -> list:
    url = f"https://insights.twilio.com/v1/Voice/Calls/{call_sid}/Events"
    resp = requests.get(url, auth=(sid, token), timeout=10)
    if resp.status_code != 200:
        return []
    return [e for e in resp.json().get("events", []) if e.get("name") in CR_EVENT_NAMES]


def _render_events(events: list) -> None:
    if not events:
        st.info("No CR events yet — events surface after the call connects (~10–30s).")
        return
    for e in sorted(events, key=lambda x: x.get("sequence_number") or 0):
        name = e.get("name", "")
        ts = (e.get("timestamp") or "")[11:19]
        data = e.get("event_data") or {}
        if name == "prompt_sent":
            with st.chat_message("user"):
                st.markdown(f"`{ts}` {data.get('voice_prompt', data.get('prompt', ''))}")
        elif name in ("first_token_received", "final_token_received"):
            with st.chat_message("assistant"):
                st.markdown(f"`{ts}` {name}: {data.get('text', data)}")
        else:
            st.caption(f"`{ts}` {name}")


def _render_ai_agent_tab(account_sid: str, auth_token: str) -> None:
    to = st.text_input("To (E.164)", placeholder="+15551234567", key="ai_to")
    from_ = st.text_input(
        "From (Twilio number)",
        value=os.getenv("TWILIO_PHONE_NUMBER", ""),
        placeholder="+15557654321",
        key="ai_from",
    )
    ws_url = st.text_input(
        "Public WebSocket URL",
        value=os.getenv("CR_WS_URL", ""),
        placeholder="wss://your-ngrok-host.ngrok-free.app/ws",
        key="ai_ws",
    )
    greeting_lang = st.selectbox(
        "Initial greeting language",
        options=list(GREETINGS.keys()),
        key="ai_greet_lang",
        help="Only sets the welcome text. The agent will follow whichever language the caller uses.",
    )
    greeting = st.text_area("Welcome greeting", value=GREETINGS[greeting_lang], key="ai_greeting")

    if st.button("Place Call", type="primary", key="ai_place"):
        if not to or not from_ or not ws_url:
            st.error("To, From, and WebSocket URL are all required.")
        elif not ws_url.startswith("wss://"):
            st.error("WebSocket URL must start with `wss://` (TLS required by ConversationRelay).")
        else:
            twiml = _build_twiml(ws_url, greeting)
            with st.expander("Generated TwiML"):
                st.code(twiml, language="xml")
            with st.spinner("Placing call..."):
                try:
                    resp = _place_call(account_sid, auth_token, to, from_, twiml)
                except requests.RequestException as e:
                    st.error(f"Request failed: {e}")
                    resp = None

            if resp is not None:
                if resp.status_code >= 400:
                    st.error(f"Status {resp.status_code}: {resp.text}")
                else:
                    data = resp.json()
                    call_sid = data.get("sid")
                    st.session_state["cr_demo_call_sid"] = call_sid
                    st.success(f"Call started: {call_sid}")
                    with st.expander("Full response"):
                        st.json(data)

    call_sid = st.session_state.get("cr_demo_call_sid")
    if call_sid:
        st.divider()
        st.markdown("**Live transcript** (polled from Voice Insights)")
        col_sid, col_refresh = st.columns([3, 1])
        with col_sid:
            st.code(call_sid, language=None)
        with col_refresh:
            if st.button("Refresh transcript", key="ai_refresh"):
                with st.spinner("Fetching events..."):
                    _render_events(_fetch_cr_events(account_sid, auth_token, call_sid))


def _render_bridge_tab(account_sid: str, auth_token: str) -> None:
    st.caption(
        "Bridge two callers who speak different languages. Each party's speech is transcribed, "
        "translated, and spoken to the other party via ElevenLabs multilingual TTS. "
        "Latency ~1–3s per turn — callers hear synthetic speech, not each other's real voice."
    )

    ws_url = st.text_input(
        "Public WebSocket URL (bridge)",
        value=os.getenv("CR_BRIDGE_WS_URL", ""),
        placeholder="wss://your-ngrok-host.ngrok-free.app/ws-bridge",
        key="br_ws",
    )
    from_number = st.text_input(
        "From (Twilio number)",
        value=os.getenv("TWILIO_PHONE_NUMBER", ""),
        placeholder="+15557654321",
        key="br_from",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**Caller A**")
        to_a = st.text_input("Phone (E.164)", key="br_to_a", placeholder="+55...")
        lang_a = st.selectbox("Greeting language", options=list(GREETINGS.keys()), index=4, key="br_lang_a")
        greeting_a = st.text_area("Greeting", value=GREETINGS[lang_a], key="br_greet_a", height=80)
    with col_b:
        st.markdown("**Caller B**")
        to_b = st.text_input("Phone (E.164)", key="br_to_b", placeholder="+1...")
        lang_b = st.selectbox("Greeting language", options=list(GREETINGS.keys()), index=0, key="br_lang_b")
        greeting_b = st.text_area("Greeting", value=GREETINGS[lang_b], key="br_greet_b", height=80)

    if st.button("Start Bridge", type="primary", key="br_start"):
        if not (ws_url and from_number and to_a and to_b):
            st.error("WebSocket URL, From, and both caller numbers are required.")
        elif not ws_url.startswith("wss://"):
            st.error("WebSocket URL must start with `wss://`.")
        else:
            session_id = uuid.uuid4().hex
            twiml_a = _build_twiml(ws_url, greeting_a, extra_params={
                "session_id": session_id, "role": "A", "greeting_lang": lang_a,
            })
            twiml_b = _build_twiml(ws_url, greeting_b, extra_params={
                "session_id": session_id, "role": "B", "greeting_lang": lang_b,
            })

            with st.expander("Generated TwiML — Caller A"):
                st.code(twiml_a, language="xml")
            with st.expander("Generated TwiML — Caller B"):
                st.code(twiml_b, language="xml")

            errors = []
            call_sid_a = call_sid_b = None
            with st.spinner("Placing calls..."):
                try:
                    resp_a = _place_call(account_sid, auth_token, to_a, from_number, twiml_a)
                    if resp_a.status_code >= 400:
                        errors.append(f"A: {resp_a.status_code} {resp_a.text}")
                    else:
                        call_sid_a = resp_a.json().get("sid")
                except requests.RequestException as e:
                    errors.append(f"A: {e}")

                try:
                    resp_b = _place_call(account_sid, auth_token, to_b, from_number, twiml_b)
                    if resp_b.status_code >= 400:
                        errors.append(f"B: {resp_b.status_code} {resp_b.text}")
                    else:
                        call_sid_b = resp_b.json().get("sid")
                except requests.RequestException as e:
                    errors.append(f"B: {e}")

            if errors:
                for err in errors:
                    st.error(err)
            if call_sid_a and call_sid_b:
                st.session_state["cr_bridge"] = {
                    "session_id": session_id,
                    "call_sid_a": call_sid_a,
                    "call_sid_b": call_sid_b,
                    "started_at": time.time(),
                }
                st.success(f"Bridge started (session {session_id[:8]}…)")

    bridge = st.session_state.get("cr_bridge")
    if bridge:
        st.divider()
        st.markdown("**Live transcripts** (Voice Insights, ~10–30s lag)")
        st.caption(f"Session `{bridge['session_id']}`")
        if st.button("Refresh transcripts", key="br_refresh"):
            events_a = _fetch_cr_events(account_sid, auth_token, bridge["call_sid_a"])
            events_b = _fetch_cr_events(account_sid, auth_token, bridge["call_sid_b"])
            tc_a, tc_b = st.columns(2)
            with tc_a:
                st.markdown(f"**Caller A** — `{bridge['call_sid_a']}`")
                _render_events(events_a)
            with tc_b:
                st.markdown(f"**Caller B** — `{bridge['call_sid_b']}`")
                _render_events(events_b)


def render():
    account_sid = st.session_state.get("account_sid", "")
    auth_token = st.session_state.get("auth_token", "")

    st.markdown(
        "<h2 style='color:#F22F46;'>ConversationRelay Demo</h2>",
        unsafe_allow_html=True,
    )

    if not account_sid or not auth_token:
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    st.info(
        "This page uses the WebSocket + LLM in `/Users/dnaidu/projects/conv-relay-scheduling`. "
        "Run `uvicorn src.main:app --port 8000` there and expose it via ngrok. "
        "Uses `multi` mode (Deepgram STT + ElevenLabs TTS) — ElevenLabs must be enabled on your account.",
        icon="ℹ️",
    )

    tab_ai, tab_bridge = st.tabs(["Outbound AI Agent", "Live Transcription"])
    with tab_ai:
        _render_ai_agent_tab(account_sid, auth_token)
    with tab_bridge:
        _render_bridge_tab(account_sid, auth_token)
