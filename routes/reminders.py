"""
Handlers for reminder-related intents.
"""
from dateutil import parser as date_parser

from database import get_session
from models.models import Reminder
from utils.datetime_parsing import to_utc, format_for_whatsapp


def handle_create_reminder(intent: dict, user) -> str:
    fire_local = date_parser.isoparse(intent["fire_at"])
    fire_utc = to_utc(fire_local, user.timezone)
    recurrence_rule = intent.get("recurrence_rule")

    with get_session() as session:
        reminder = Reminder(
            user_id=user.id,
            text=intent["text"],
            fire_at=fire_utc,
            recurrence_rule=recurrence_rule,
        )
        session.add(reminder)
        session.commit()
        reminder_text = reminder.text  # capture before session closes

    when_str = format_for_whatsapp(fire_utc, user.timezone)
    recurrence_note = ""
    if recurrence_rule:
        recurrence_note = f" (repeating: {_describe_recurrence(recurrence_rule)})"
    return f"⏰ Reminder set: \"{reminder_text}\" on {when_str}{recurrence_note}."


def handle_list_reminders(intent: dict, user) -> str:
    with get_session() as session:
        reminders = (
            session.query(Reminder)
            .filter(Reminder.user_id == user.id, Reminder.status == "pending")
            .order_by(Reminder.fire_at)
            .all()
        )

        if not reminders:
            return "You have no pending reminders. 👍"

        lines = ["⏰ Your pending reminders:"]
        for r in reminders:
            when_str = format_for_whatsapp(r.fire_at, user.timezone)
            recurrence_note = f" (repeats {_describe_recurrence(r.recurrence_rule)})" if r.recurrence_rule else ""
            lines.append(f"• {r.text} — {when_str}{recurrence_note}")
        return "\n".join(lines)


def _describe_recurrence(rule: str) -> str:
    if rule == "daily":
        return "daily"
    if rule.startswith("weekly:"):
        day = rule.split(":")[1].title()
        return f"every {day}"
    if rule.startswith("monthly:"):
        day_num = rule.split(":")[1]
        return f"monthly on the {day_num}{_ordinal_suffix(int(day_num))}"
    return rule


def _ordinal_suffix(n: int) -> str:
    if 11 <= n % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
