"""
Datetime helpers: timezone conversion and recurrence calculation.

We deliberately do NOT try to parse natural language dates ourselves with
regex (e.g. "next Tuesday at 9am"). That's handled by Claude in
services/intent_parser.py, which is given the user's current local time
and asked to return an ISO 8601 datetime directly. This module only
handles the mechanical parts: timezone conversion and figuring out the
next occurrence of a recurring reminder.
"""
from datetime import datetime, timedelta
import pytz

WEEKDAY_MAP = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6
}


def to_utc(local_dt: datetime, tz_name: str) -> datetime:
    """Convert a naive local datetime to a naive UTC datetime for storage."""
    tz = pytz.timezone(tz_name)
    localized = tz.localize(local_dt) if local_dt.tzinfo is None else local_dt
    return localized.astimezone(pytz.utc).replace(tzinfo=None)


def to_local(utc_dt: datetime, tz_name: str) -> datetime:
    """Convert a naive UTC datetime (as stored in the DB) to local time for display."""
    tz = pytz.timezone(tz_name)
    aware_utc = pytz.utc.localize(utc_dt) if utc_dt.tzinfo is None else utc_dt
    return aware_utc.astimezone(tz)


def now_in_timezone(tz_name: str) -> datetime:
    return datetime.now(pytz.timezone(tz_name))


def compute_next_occurrence(current_fire_at_utc: datetime, recurrence_rule: str, tz_name: str) -> datetime:
    """
    Given the UTC datetime a recurring reminder just fired at, compute the
    next UTC datetime it should fire at, preserving the same local
    hour:minute the user originally asked for (so DST shifts don't drift
    the reminder by an hour).

    Supported recurrence_rule formats:
      - "daily"
      - "weekly:MON" (single weekday, case-insensitive 3-letter code)
      - "monthly:15" (day-of-month, 1-31; clamps to last day if month is shorter)
    """
    local_dt = to_local(current_fire_at_utc, tz_name)
    hour, minute = local_dt.hour, local_dt.minute

    if recurrence_rule == "daily":
        next_local = local_dt + timedelta(days=1)

    elif recurrence_rule.startswith("weekly:"):
        target_weekday = WEEKDAY_MAP[recurrence_rule.split(":")[1].upper()]
        days_ahead = (target_weekday - local_dt.weekday()) % 7
        days_ahead = days_ahead if days_ahead != 0 else 7  # always move forward
        next_local = local_dt + timedelta(days=days_ahead)

    elif recurrence_rule.startswith("monthly:"):
        target_day = int(recurrence_rule.split(":")[1])
        month = local_dt.month + 1 if local_dt.month < 12 else 1
        year = local_dt.year if local_dt.month < 12 else local_dt.year + 1
        # Clamp to last valid day of that month (e.g. requested 31st in a 30-day month)
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        day = min(target_day, last_day)
        next_local = local_dt.replace(year=year, month=month, day=day)

    else:
        raise ValueError(f"Unsupported recurrence_rule: {recurrence_rule}")

    next_local = next_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    tz = pytz.timezone(tz_name)
    if next_local.tzinfo is None:
        next_local = tz.localize(next_local)
    return next_local.astimezone(pytz.utc).replace(tzinfo=None)


def format_for_whatsapp(dt_utc: datetime, tz_name: str) -> str:
    """Human-friendly local time string for WhatsApp replies, e.g. 'Tue 25 Jun, 3:00 PM'."""
    local_dt = to_local(dt_utc, tz_name)
    return local_dt.strftime("%a %d %b, %-I:%M %p")
