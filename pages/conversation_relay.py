import os
import time

import requests
import streamlit as st
from twilio.twiml.voice_response import Connect, ConversationRelay, VoiceResponse

from pages.inspector import record_request


LANGUAGE_VOICES = {
    "en-US": {"label": "English (US)", "tts_provider": "Amazon", "voice": "Joanna-Neural"},
    "es-US": {"label": "Spanish (US)", "tts_provider": "Amazon", "voice": "Lupe-Neural"},
    "fr-FR": {"label": "French (FR)", "tts_provider": "Amazon", "voice": "Lea-Neural"},
    "de-DE": {"label": "German (DE)", "tts_provider": "Amazon", "voice": "Vicki-Neural"},
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


def _build_twiml(ws_url: str, language: str, greeting: str) -> str:
    vr = VoiceResponse()
    connect = Connect()
    cr = ConversationRelay(
        url=ws_url,
        welcome_greeting=greeting,
        language=language,
        transcription_language=language,
        tts_provider=LANGUAGE_VOICES[language]["tts_provider"],
        voice=LANGUAGE_VOICES[language]["voice"],
        transcription_provider="Deepgram",
        speech_model="nova-3-general",
    )
    for code, cfg in LANGUAGE_VOICES.items():
        cr.language(
            code=code,
            tts_provider=cfg["tts_provider"],
            voice=cfg["voice"],
            transcription_provider="Deepgram",
        )
    cr.parameter(name="language", value=language)
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
    events = resp.json().get("events", [])
    return [e for e in events if e.get("name") in CR_EVENT_NAMES]


def render():
    account_sid = st.session_state.get("account_sid", "")
    auth_token = st.session_state.get("auth_token", "")

    st.markdown(
        "<h2 style='color:#F22F46;'>ConversationRelay Demo</h2>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Place an outbound call to an AI agent. Pick a language; the agent will greet, listen, "
        "and reply in that language via Twilio ConversationRelay."
    )

    if not account_sid or not auth_token:
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    st.info(
        "This page reuses the WebSocket + LLM in `/Users/dnaidu/projects/conv-relay-scheduling`. "
        "Run `uvicorn src.main:app --port 8000` there and expose it via ngrok, then paste the "
        "`wss://<host>/ws` URL below.",
        icon="ℹ️",
    )

    to = st.text_input("To (E.164)", placeholder="+15551234567")
    from_ = st.text_input(
        "From (Twilio number)",
        value=os.getenv("TWILIO_PHONE_NUMBER", ""),
        placeholder="+15557654321",
    )
    ws_url = st.text_input(
        "Public WebSocket URL",
        value=os.getenv("CR_WS_URL", ""),
        placeholder="wss://your-ngrok-host.ngrok-free.app/ws",
    )
    language = st.selectbox(
        "Language",
        options=list(LANGUAGE_VOICES.keys()),
        format_func=lambda c: f"{c} — {LANGUAGE_VOICES[c]['label']}",
    )
    default_greetings = {
        "en-US": "Hello, this is your AI assistant. How can I help you today?",
        "es-US": "Hola, soy su asistente de inteligencia artificial. ¿Cómo puedo ayudarle hoy?",
        "fr-FR": "Bonjour, je suis votre assistant IA. Comment puis-je vous aider aujourd'hui ?",
        "de-DE": "Hallo, ich bin Ihr KI-Assistent. Wie kann ich Ihnen heute helfen?",
    }
    greeting = st.text_area("Welcome greeting", value=default_greetings[language])

    if st.button("Place Call", type="primary"):
        if not to or not from_ or not ws_url:
            st.error("To, From, and WebSocket URL are all required.")
        elif not ws_url.startswith("wss://"):
            st.error("WebSocket URL must start with `wss://` (TLS required by ConversationRelay).")
        else:
            twiml = _build_twiml(ws_url, language, greeting)
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
                    st.session_state["cr_demo_started_at"] = time.time()
                    st.success(f"Call started: {call_sid}")
                    with st.expander("Full response"):
                        st.json(data)

    call_sid = st.session_state.get("cr_demo_call_sid")
    if call_sid:
        st.divider()
        st.markdown("**Live transcript** (polled from Voice Insights)")
        st.caption(
            "Voice Insights events lag by ~10–30s. For real-time transcripts open the "
            "conv-relay-scheduling live-calls page at `/pages/live-calls`."
        )
        col_sid, col_refresh = st.columns([3, 1])
        with col_sid:
            st.code(call_sid, language=None)
        with col_refresh:
            refresh = st.button("Refresh transcript")

        if refresh:
            with st.spinner("Fetching events..."):
                events = _fetch_cr_events(account_sid, auth_token, call_sid)
            if not events:
                st.info("No CR events yet — events surface after the call connects.")
            else:
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
