import asyncio
import json
import os
import re

import streamlit as st
from twilio.rest import Client
from tac import TAC, TACConfig
from tac.channels.sms import SMSChannel, SMSChannelConfig
from tac.channels.voice import VoiceChannel, VoiceChannelConfig
from tac.models.outbound import InitiateMessagingConversationOptions, InitiateVoiceConversationOptions


def _client():
    return Client(st.session_state["account_sid"], st.session_state["auth_token"])


def render():
    st.markdown(
        "<h2 style='color:#F22F46;'>Actions</h2>",
        unsafe_allow_html=True,
    )

    if not st.session_state.get("account_sid") or not st.session_state.get("auth_token"):
        st.warning("Enter your Twilio credentials in the sidebar to get started.")
        return

    tab_send_sms, tab_tac_sms, tab_tac_voice = st.tabs(
        ["Send SMS to customer", "TAC outbound SMS", "TAC outbound call"]
    )

    with tab_send_sms:
        st.subheader("Send SMS to customer")

        workspace_sid = os.getenv("FLEX_APP_WORKSPACE_SID", "")
        workflow_sid = os.getenv("FLEX_APP_WORKFLOW_SID", "")
        queue_sid = os.getenv("FLEX_APP_QUEUE_SID", "")
        worker_sid = os.getenv("FLEX_APP_WORKER_SID", "")
        default_from = os.getenv("TWILIO_PHONE_NUMBER", "")
        existing_sid = None

        col1, col2 = st.columns(2)
        with col1:
            to = st.text_input("To (customer number)", placeholder="+447876762080", key="sms_to")
            # from_ = st.text_input("From (Twilio number)", value=default_from, placeholder=default_from, key="sms_from")
        with col2:
            # author = st.text_input("Author (agent name)", placeholder="agent@example.com", key="sms_author")
            sms_text = st.text_area("Message", placeholder="Hello from Twilio", key="sms_text")

        if st.button("Send SMS", type="primary", key="btn_send_sms"):
            missing = [k for k, v in {"To": to, "Message": sms_text}.items() if not v]
            if missing:
                st.error(f"Required fields missing: {', '.join(missing)}")
                st.stop()

            client = _client()
            agent_name = ""

            # Step 1: create a fresh conversation
            with st.spinner("Creating conversation..."):
                conversation = client.conversations.v1.conversations.create()
            st.info(f"Created conversation: {conversation.sid}")

            # Step 2: add SMS participant — may fail if number already in an active conversation
            with st.spinner("Adding participant..."):
                try:
                    client.conversations.v1.conversations(conversation.sid).participants.create(
                        messaging_binding_address=to,
                        messaging_binding_proxy_address=default_from,
                    )
                    st.info("Participant added to new conversation.")
                except Exception as e:
                    error_str = str(e)
                    match = re.search(r"Conversation (CH[a-f0-9]+)", error_str)
                    if not match:
                        st.error(f"Failed to add participant: {e}")
                        client.conversations.v1.conversations(conversation.sid).delete()
                        st.stop()

                    existing_sid = match.group(1)
                    st.info(f"Number already in conversation {existing_sid} — using existing.")

                    existing_conversation = client.conversations.v1.conversations(existing_sid).fetch()

                    participants = client.conversations.v1.conversations(existing_sid).participants.list()
                    for participant in participants:
                        if participant.identity:
                            agent_identity = participant.identity
                            workers = client.taskrouter.v1.workspaces(workspace_sid).workers.list(friendly_name=agent_identity)
                            if workers:
                                agent_name = json.loads(workers[0].attributes).get("name", "")

                    client.conversations.v1.conversations(conversation.sid).delete()
                    st.info(f"Deleted unused conversation {conversation.sid}.")
                    # st.info(f"Workspace sid: {workspace_sid}. Workflow sid: {workflow_sid}. Queue sid: {queue_sid}. Worker sid: {worker_sid}.")
                    conversation = existing_conversation

            # Step 3: create Flex interaction
            with st.spinner("Creating Flex interaction..."):
                interaction = client.flex_api.v1.interaction.create(
                    channel={
                        "type": "sms",
                        "initiated_by": "agent",
                        "properties": {"media_channel_sid": existing_sid},
                    },
                    routing={
                        "properties": {
                            "workspace_sid": workspace_sid,
                            "workflow_sid": workflow_sid,
                            "queue_sid": queue_sid,
                            "worker_sid": worker_sid,
                            "task_channel_unique_name": "chat",
                            "media_channel_sid": existing_sid,
                            "attributes": {
                                "customerName": "Customer",
                                "from": default_from,
                                "direction": "outbound",
                                "customerAddress": to,
                                "twilioNumber": default_from,
                            },
                        }
                    },
                )

            task_attributes = interaction.routing["properties"]["attributes"]
            # st.info(f"Interaction task atttributes {task_attributes}")
            conv_sid = json.loads(task_attributes).get("conversationSid")
            st.info(f"Interaction created. Sending message via conversation: {conv_sid}")

            # Step 4: send the message
            with st.spinner("Sending message..."):
                message = client.conversations.v1.conversations(conv_sid).messages.create(
                    author=agent_name,
                    body=sms_text,
                )

            st.success("SMS sent successfully.")
            with st.expander("Message response"):
                st.json({"sid": message.sid, "author": message.author, "body": message.body})

    with tab_tac_sms:
        st.subheader("TAC outbound SMS")

        tac_sms_to = st.text_input("To (customer number)", placeholder="+16505551234", key="tac_sms_to")
        tac_sms_text = st.text_area("Message", placeholder="Hi! Your order has shipped.", key="tac_sms_text")

        if st.button("Send SMS", type="primary", key="btn_tac_sms"):
            missing = [k for k, v in {"To": tac_sms_to, "Message": tac_sms_text}.items() if not v]
            if missing:
                st.error(f"Required fields missing: {', '.join(missing)}")
                st.stop()

            with st.spinner("Initiating outbound SMS conversation..."):
                try:
                    tac = TAC(config=TACConfig.from_env())
                    sms_channel = SMSChannel(tac, config=SMSChannelConfig(memory_mode="always"))
                    result = asyncio.run(
                        sms_channel.initiate_outbound_conversation(
                            InitiateMessagingConversationOptions(
                                to=tac_sms_to,
                                message=tac_sms_text,
                            )
                        )
                    )
                    st.success("Outbound SMS conversation initiated.")
                    with st.expander("Result"):
                        st.json({"conversation_id": result.conversation_id} if hasattr(result, "conversation_id") else str(result))
                except Exception as e:
                    st.error(f"Failed: {e}")

    with tab_tac_voice:
        st.subheader("TAC outbound call")

        public_domain = os.getenv("TWILIO_VOICE_PUBLIC_DOMAIN", "")

        tac_voice_to = st.text_input("To (customer number)", placeholder="+16505551234", key="tac_voice_to")
        tac_voice_domain = os.getenv("TWILIO_VOICE_PUBLIC_DOMAIN", "")
        tac_voice_greeting = st.text_input("Welcome greeting (optional)", placeholder="Hi! This is an AI assistant calling from Acme Corp.", key="tac_voice_greeting")

        if st.button("Start call", type="primary", key="btn_tac_voice"):
            missing = [k for k, v in {"To": tac_voice_to, "Public domain": tac_voice_domain}.items() if not v]
            if missing:
                st.error(f"Required fields missing: {', '.join(missing)}")
                st.stop()

            with st.spinner("Initiating outbound call..."):
                try:
                    tac = TAC(config=TACConfig.from_env())
                    voice_channel = VoiceChannel(tac, config=VoiceChannelConfig(memory_mode="always"))
                    opts = InitiateVoiceConversationOptions(
                        to=tac_voice_to,
                        websocket_url=f"wss://{tac_voice_domain}/ws",
                        action_url=f"https://{tac_voice_domain}/conversation-relay-callback",
                    )
                    if tac_voice_greeting:
                        opts.welcome_greeting = tac_voice_greeting
                    result = asyncio.run(voice_channel.initiate_outbound_conversation(opts))
                    st.success("Outbound call initiated.")
                    with st.expander("Result"):
                        st.json({"call_sid": result.call_sid} if hasattr(result, "call_sid") else str(result))
                except Exception as e:
                    st.error(f"Failed: {e}")
