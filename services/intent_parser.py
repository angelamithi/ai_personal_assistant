"""
Intent parsing: turn free-form text (typed or transcribed from voice) into
a structured intent the rest of the app can act on.

Design: a single Claude call per inbound message, given:
  - the user's current local time and timezone (so "tomorrow at 9am" /
    "next Tuesday" resolve correctly)
  - the message text
  - whether there's a pending conversation_state (so "tomorrow at 9am" as
    a standalone follow-up message gets attached to the right prior intent)

We ask Claude to return ONLY JSON matching one of the schemas below, never
prose, so the route handlers can deserialize and act directly.
"""
import json
import os
from datetime import datetime

from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SYSTEM_PROMPT = """You are the intent-parsing layer for a WhatsApp personal assistant. \
Given a user's message, classify it into exactly one intent and extract the relevant \
fields. Respond with ONLY a single JSON object, no prose, no markdown fences.

Possible intents and their required fields:

- create_event: {"intent": "create_event", "title": str, "start_time": "<ISO 8601>", \
"end_time": "<ISO 8601 or null>", "notes": str or null}
- list_events: {"intent": "list_events", "range": "today" | "tomorrow" | "week" | "all"}
- cancel_event: {"intent": "cancel_event", "title_hint": str, "date_hint": str or null}
- create_reminder: {"intent": "create_reminder", "text": str, "fire_at": "<ISO 8601>", \
"recurrence_rule": null | "daily" | "weekly:MON" (etc, 3-letter weekday) | "monthly:15" (day number)}
- list_reminders: {"intent": "list_reminders"}
- create_todo: {"intent": "create_todo", "text": str, "due_date": "<ISO 8601 or null>"}
- list_todos: {"intent": "list_todos"}
- complete_todo: {"intent": "complete_todo", "text_hint": str}
- draft_message: {"intent": "draft_message", "context": str, "recipient_hint": str or null, \
"tone": str or null}
- draft_email: {"intent": "draft_email", "context": str, "recipient_hint": str or null, \
"tone": str or null}
- needs_clarification: {"intent": "needs_clarification", "question": str}
- general_chat: {"intent": "general_chat", "reply": str}

Rules:
- All datetimes you output MUST be ISO 8601 WITHOUT timezone offset, expressed in the \
user's LOCAL time (it will be localized using their stored timezone afterward). \
You are given the user's current local date/time below — use it to resolve relative \
references like "tomorrow", "next Tuesday", "in 2 hours".
- If a reminder or event request is missing a clear time, use "needs_clarification" \
and ask a short, specific question.
- If the message is ambiguous between intents, prefer "needs_clarification" over guessing.
- For draft_message / draft_email, just extract what the user told you about the \
content/context — do not write the draft yourself here, that happens in a separate step.
- For casual conversation, greetings, or anything not matching another intent, use \
general_chat with a short, warm reply in the "reply" field.
"""


def parse_intent(message_text: str, user_local_now: datetime, pending_context: dict | None = None) -> dict:
    context_note = ""
    if pending_context:
        context_note = (
            f"\n\nNote: there is a pending unfinished request from the user: "
            f"{json.dumps(pending_context)}. If this new message answers it "
            f"(e.g. supplies a missing time), merge the information and return "
            f"the completed intent rather than needs_clarification again."
        )

    user_message = (
        f"Current local date/time for this user: {user_local_now.isoformat()}\n"
        f"User's message: \"{message_text}\""
        f"{context_note}"
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    # Defensive: strip markdown fences if the model adds them anyway
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "intent": "needs_clarification",
            "question": "Sorry, I didn't quite catch that — could you rephrase?",
        }
