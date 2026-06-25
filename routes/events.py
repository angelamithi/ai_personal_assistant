"""
Handlers for calendar-event-related intents. Each function takes the
already-parsed intent dict plus the User row, does the DB work, and
returns the WhatsApp reply text. Keeping these as plain functions (not
FastAPI routes) since they're invoked directly from webhook_server.py's
dispatch logic, not via separate HTTP endpoints.
"""
from datetime import datetime, timedelta

from dateutil import parser as date_parser
from sqlalchemy import and_

from database import get_session
from models.models import Event
from utils.datetime_parsing import to_utc, to_local, format_for_whatsapp, now_in_timezone


def handle_create_event(intent: dict, user) -> str:
    start_local = date_parser.isoparse(intent["start_time"])
    start_utc = to_utc(start_local, user.timezone)

    end_utc = None
    if intent.get("end_time"):
        end_local = date_parser.isoparse(intent["end_time"])
        end_utc = to_utc(end_local, user.timezone)

    with get_session() as session:
        event = Event(
            user_id=user.id,
            title=intent["title"],
            notes=intent.get("notes"),
            start_time=start_utc,
            end_time=end_utc,
        )
        session.add(event)
        session.commit()
        title = event.title  # capture before session closes, to avoid DetachedInstanceError

    when_str = format_for_whatsapp(start_utc, user.timezone)
    return f"✅ Got it — \"{title}\" on {when_str}. I'll remind you 30 min before."


def handle_list_events(intent: dict, user) -> str:
    range_type = intent.get("range", "today")
    now_local = now_in_timezone(user.timezone)

    if range_type == "today":
        start_window = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_window = start_window + timedelta(days=1)
    elif range_type == "tomorrow":
        start_window = (now_local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_window = start_window + timedelta(days=1)
    elif range_type == "week":
        start_window = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        end_window = start_window + timedelta(days=7)
    else:  # "all"
        start_window = None
        end_window = None

    with get_session() as session:
        query = session.query(Event).filter(
            Event.user_id == user.id, Event.status == "upcoming"
        )
        if start_window:
            start_utc = to_utc(start_window.replace(tzinfo=None), user.timezone)
            end_utc = to_utc(end_window.replace(tzinfo=None), user.timezone)
            query = query.filter(and_(Event.start_time >= start_utc, Event.start_time < end_utc))
        events = query.order_by(Event.start_time).all()

    if not events:
        return "You have nothing on your calendar for that period. 🎉"

    lines = ["📅 Here's what's coming up:"]
    for event in events:
        when_str = format_for_whatsapp(event.start_time, user.timezone)
        lines.append(f"• {event.title} — {when_str}")
    return "\n".join(lines)


def handle_cancel_event(intent: dict, user) -> str:
    title_hint = intent["title_hint"].lower()

    with get_session() as session:
        query = session.query(Event).filter(
            Event.user_id == user.id,
            Event.status == "upcoming",
            Event.title.ilike(f"%{title_hint}%"),
        )
        matches = query.all()

        if not matches:
            return f"I couldn't find an upcoming event matching \"{intent['title_hint']}\"."

        if len(matches) > 1:
            lines = ["I found a few matches — which one did you mean?"]
            for m in matches:
                lines.append(f"• {m.title} — {format_for_whatsapp(m.start_time, user.timezone)}")
            return "\n".join(lines)

        event = matches[0]
        event.status = "cancelled"
        session.commit()
        return f"🗑️ Cancelled \"{event.title}\"."
