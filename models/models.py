"""
Core data models.

Design notes:
- Everything is scoped to a `user_id` (your phone number maps to one User
  row). Built this way so it's trivial to support more than one person
  later (e.g. a family member) without restructuring.
- `Reminder.recurrence_rule` is a simple string format we parse ourselves
  rather than pulling in a full RFC 5545 RRULE library, since the supported
  patterns are intentionally small: None, "daily", "weekly:MON", "monthly:15".
  See utils/datetime_parsing.py for the parsing/next-occurrence logic.
- `ConversationState` exists for short multi-turn exchanges, e.g.:
    User: "remind me to call the dentist"
    Bot:  "When should I remind you?"
    User: "tomorrow at 9am"
  Without this, the second message has no context to attach to.
"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    phone_number = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    timezone = Column(String, default="Africa/Nairobi", nullable=False)
    briefing_time = Column(String, default="07:00", nullable=False)  # "HH:MM" in user's tz
    briefing_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="user", cascade="all, delete-orphan")
    todos = relationship("Todo", back_populates="user", cascade="all, delete-orphan")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    notes = Column(Text, nullable=True)
    start_time = Column(DateTime, nullable=False)  # stored in UTC
    end_time = Column(DateTime, nullable=True)      # stored in UTC
    reminder_lead_minutes = Column(Integer, default=30, nullable=False)
    reminder_sent = Column(Boolean, default=False, nullable=False)
    status = Column(String, default="upcoming", nullable=False)  # upcoming|done|cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="events")


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text = Column(String, nullable=False)
    fire_at = Column(DateTime, nullable=False)  # stored in UTC; next/only occurrence
    recurrence_rule = Column(String, nullable=True)  # None | "daily" | "weekly:MON" | "monthly:15"
    last_sent_at = Column(DateTime, nullable=True)
    status = Column(String, default="pending", nullable=False)  # pending|done|cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="reminders")


class Todo(Base):
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    text = Column(String, nullable=False)
    status = Column(String, default="open", nullable=False)  # open|done
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="todos")


class ConversationState(Base):
    """
    Holds short-lived context for multi-turn exchanges. One row per user;
    overwritten/cleared as conversations resolve. `pending_data` stores
    whatever partial structured fields we've gathered so far as JSON.
    """
    __tablename__ = "conversation_state"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    awaiting = Column(String, nullable=True)  # e.g. "reminder_time", "event_confirmation"
    pending_data = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
