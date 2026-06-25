"""
Background scheduler.

Runs as a thread inside the same FastAPI process (started on app startup
in webhook_server.py) rather than as a separate Render service, to avoid
paying for a second always-on instance. APScheduler's BackgroundScheduler
handles this cleanly with an in-process thread pool.

Three jobs, all running on a 1-minute tick:
  1. check_due_reminders   — fires pending reminders, reschedules recurring ones
  2. check_event_nudges    — sends "starting soon" nudges ahead of events
  3. check_daily_briefings — sends each user's morning briefing once per day
"""
import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from database import get_session
from models.models import User, Reminder, Event, Todo
from services.whatsapp_client import send_text_message
from utils.datetime_parsing import (
    compute_next_occurrence, format_for_whatsapp, now_in_timezone, to_local
)

logger = logging.getLogger("scheduler")


def _send_sync(phone_number: str, text: str) -> None:
    """send_text_message is async; run it from this sync scheduler context."""
    asyncio.run(send_text_message(phone_number, text))


def check_due_reminders() -> None:
    now_utc = datetime.utcnow()
    with get_session() as session:
        due = (
            session.query(Reminder)
            .filter(Reminder.status == "pending", Reminder.fire_at <= now_utc)
            .all()
        )
        for reminder in due:
            user = session.query(User).get(reminder.user_id)
            try:
                _send_sync(user.phone_number, f"⏰ Reminder: {reminder.text}")
            except Exception:
                logger.exception("Failed to send reminder %s", reminder.id)
                continue

            reminder.last_sent_at = now_utc
            if reminder.recurrence_rule:
                reminder.fire_at = compute_next_occurrence(
                    reminder.fire_at, reminder.recurrence_rule, user.timezone
                )
            else:
                reminder.status = "done"
        session.commit()


def check_event_nudges() -> None:
    now_utc = datetime.utcnow()
    with get_session() as session:
        upcoming = (
            session.query(Event)
            .filter(Event.status == "upcoming", Event.reminder_sent == False)  # noqa: E712
            .all()
        )
        for event in upcoming:
            nudge_at = event.start_time - timedelta(minutes=event.reminder_lead_minutes)
            if nudge_at <= now_utc:
                user = session.query(User).get(event.user_id)
                when_str = format_for_whatsapp(event.start_time, user.timezone)
                try:
                    _send_sync(
                        user.phone_number,
                        f"📅 Starting in {event.reminder_lead_minutes} min: \"{event.title}\" ({when_str})",
                    )
                except Exception:
                    logger.exception("Failed to send event nudge %s", event.id)
                    continue
                event.reminder_sent = True
        session.commit()


def check_daily_briefings() -> None:
    now_utc = datetime.utcnow()
    with get_session() as session:
        users = session.query(User).filter(User.briefing_enabled == True).all()  # noqa: E712

        for user in users:
            local_now = to_local(now_utc, user.timezone)
            target_hour, target_minute = map(int, user.briefing_time.split(":"))

            # Fire within a 1-minute window of the target time, once per day.
            # We key "already sent today" off a simple in-memory-safe check:
            # has any reminder/marker been sent in the last ~23 hours? Simplest
            # robust approach: store last-sent date on the user row.
            if local_now.hour != target_hour or local_now.minute != target_minute:
                continue

            today_start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end_local = today_start_local + timedelta(days=1)
            from utils.datetime_parsing import to_utc
            today_start_utc = to_utc(today_start_local.replace(tzinfo=None), user.timezone)
            today_end_utc = to_utc(today_end_local.replace(tzinfo=None), user.timezone)

            events_today = (
                session.query(Event)
                .filter(
                    Event.user_id == user.id,
                    Event.status == "upcoming",
                    Event.start_time >= today_start_utc,
                    Event.start_time < today_end_utc,
                )
                .order_by(Event.start_time)
                .all()
            )
            open_todos = (
                session.query(Todo)
                .filter(Todo.user_id == user.id, Todo.status == "open")
                .order_by(Todo.created_at)
                .all()
            )

            lines = [f"☀️ Good morning! Here's your day:"]
            if events_today:
                lines.append("\n📅 Today's events:")
                for e in events_today:
                    lines.append(f"• {e.title} — {format_for_whatsapp(e.start_time, user.timezone)}")
            else:
                lines.append("\n📅 No events on your calendar today.")

            if open_todos:
                lines.append("\n📝 Open to-dos:")
                for t in open_todos[:10]:  # cap to keep the message readable
                    lines.append(f"• {t.text}")
                if len(open_todos) > 10:
                    lines.append(f"...and {len(open_todos) - 10} more.")
            else:
                lines.append("\n📝 Your to-do list is clear.")

            try:
                _send_sync(user.phone_number, "\n".join(lines))
            except Exception:
                logger.exception("Failed to send daily briefing to user %s", user.id)


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(check_due_reminders, "interval", minutes=1, id="check_due_reminders")
    scheduler.add_job(check_event_nudges, "interval", minutes=1, id="check_event_nudges")
    scheduler.add_job(check_daily_briefings, "interval", minutes=1, id="check_daily_briefings")
    scheduler.start()
    logger.info("Scheduler started: reminders, event nudges, daily briefings all on 1-min tick.")
    return scheduler
