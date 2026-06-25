"""
Main FastAPI app.

Responsibilities:
- GET /webhook  — Meta's webhook verification handshake
- POST /webhook — receives incoming WhatsApp messages (text or voice),
  transcribes voice if needed, runs intent parsing, dispatches to the
  matching handler, replies in WhatsApp.
- Starts the background scheduler on app startup.

Single-user note: USER_PHONE_NUMBER in env identifies "you" for now. The
data model supports multiple users already (everything is keyed by
user.id), so adding a second person later is just a matter of looking up
the inbound sender's number instead of trusting only the env var — left
as a clean extension point, not built out yet since you're the only user.
"""
import os
import logging

from fastapi import FastAPI, Request, Response

from database import get_session
from models.models import User, ConversationState
from services.whatsapp_client import send_text_message, get_media_url, download_media
from services.transcription import transcribe_audio
from services.intent_parser import parse_intent
from services.drafting import draft_email, draft_message
from services.scheduler import start_scheduler
from utils.datetime_parsing import now_in_timezone
from routes.events import handle_create_event, handle_list_events, handle_cancel_event
from routes.reminders import handle_create_reminder, handle_list_reminders
from routes.todos import handle_create_todo, handle_list_todos, handle_complete_todo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("webhook_server")

app = FastAPI()

WHATSAPP_VERIFY_TOKEN = os.environ["WHATSAPP_VERIFY_TOKEN"]
DEFAULT_TIMEZONE = os.environ.get("DEFAULT_TIMEZONE", "Africa/Nairobi")

INTENT_HANDLERS = {
    "create_event": handle_create_event,
    "list_events": handle_list_events,
    "cancel_event": handle_cancel_event,
    "create_reminder": handle_create_reminder,
    "list_reminders": handle_list_reminders,
    "create_todo": handle_create_todo,
    "list_todos": handle_list_todos,
    "complete_todo": handle_complete_todo,
}


@app.on_event("startup")
def on_startup():
    start_scheduler()


@app.get("/webhook")
def verify_webhook(request: Request):
    """Meta's one-time webhook verification handshake."""
    params = request.query_params
    if params.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
        return Response(content=params.get("hub.challenge", ""), media_type="text/plain")
    return Response(status_code=403)


@app.post("/webhook")
async def receive_webhook(request: Request):
    body = await request.json()

    try:
        entry = body["entry"][0]["changes"][0]["value"]
        messages = entry.get("messages")
        if not messages:
            return {"status": "ignored"}  # e.g. status/read receipts, no message content

        message = messages[0]
        from_number = message["from"]
        message_type = message["type"]
    except (KeyError, IndexError):
        logger.warning("Malformed webhook payload, ignoring.")
        return {"status": "ignored"}

    user = get_or_create_user(from_number)

    if message_type == "text":
        text = message["text"]["body"]
    elif message_type == "audio":
        media_id = message["audio"]["id"]
        media_url = await get_media_url(media_id)
        audio_bytes = await download_media(media_url)
        text = transcribe_audio(audio_bytes)
    else:
        await send_text_message(from_number, "I can only handle text and voice notes right now 🙂")
        return {"status": "ok"}

    reply = await process_message(text, user)
    await send_text_message(from_number, reply)
    return {"status": "ok"}


def get_or_create_user(phone_number: str) -> User:
    with get_session() as session:
        user = session.query(User).filter(User.phone_number == phone_number).first()
        if not user:
            user = User(phone_number=phone_number, timezone=DEFAULT_TIMEZONE)
            session.add(user)
            session.commit()
            session.refresh(user)
        # Detach-safe copy of fields we need outside the session
        session.expunge(user)
        return user


async def process_message(text: str, user: User) -> str:
    pending_context = None
    with get_session() as session:
        state = session.query(ConversationState).filter(
            ConversationState.user_id == user.id
        ).first()
        if state and state.awaiting:
            pending_context = state.pending_data

    local_now = now_in_timezone(user.timezone)
    intent = parse_intent(text, local_now, pending_context)
    intent_type = intent.get("intent")

    if intent_type == "needs_clarification":
        save_conversation_state(user.id, "clarification", intent)
        return intent["question"]

    # Any successfully resolved intent clears prior pending state
    clear_conversation_state(user.id)

    if intent_type == "general_chat":
        return intent["reply"]

    if intent_type == "draft_email":
        return "✉️ Here's your draft:\n\n" + draft_email(
            intent["context"], intent.get("recipient_hint"), intent.get("tone")
        )

    if intent_type == "draft_message":
        return "💬 Here's a draft:\n\n" + draft_message(
            intent["context"], intent.get("recipient_hint"), intent.get("tone")
        )

    handler = INTENT_HANDLERS.get(intent_type)
    if handler:
        return handler(intent, user)

    return "Sorry, I'm not sure how to help with that yet."


def save_conversation_state(user_id: int, awaiting: str, pending_data: dict) -> None:
    with get_session() as session:
        state = session.query(ConversationState).filter(
            ConversationState.user_id == user_id
        ).first()
        if state:
            state.awaiting = awaiting
            state.pending_data = pending_data
        else:
            state = ConversationState(
                user_id=user_id, awaiting=awaiting, pending_data=pending_data
            )
            session.add(state)
        session.commit()


def clear_conversation_state(user_id: int) -> None:
    with get_session() as session:
        state = session.query(ConversationState).filter(
            ConversationState.user_id == user_id
        ).first()
        if state:
            state.awaiting = None
            state.pending_data = None
            session.commit()
