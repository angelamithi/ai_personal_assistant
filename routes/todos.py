"""
Handlers for to-do list intents.
"""
from dateutil import parser as date_parser

from database import get_session
from models.models import Todo
from utils.datetime_parsing import to_utc, format_for_whatsapp


def handle_create_todo(intent: dict, user) -> str:
    due_utc = None
    if intent.get("due_date"):
        due_local = date_parser.isoparse(intent["due_date"])
        due_utc = to_utc(due_local, user.timezone)

    with get_session() as session:
        todo = Todo(user_id=user.id, text=intent["text"], due_date=due_utc)
        session.add(todo)
        session.commit()
        todo_text = todo.text  # capture before session closes

    due_note = f" (due {format_for_whatsapp(due_utc, user.timezone)})" if due_utc else ""
    return f"📝 Added to your to-do list: \"{todo_text}\"{due_note}."


def handle_list_todos(intent: dict, user) -> str:
    with get_session() as session:
        todos = (
            session.query(Todo)
            .filter(Todo.user_id == user.id, Todo.status == "open")
            .order_by(Todo.created_at)
            .all()
        )

        if not todos:
            return "Your to-do list is empty. ✨"

        lines = ["📝 Your open to-dos:"]
        for i, t in enumerate(todos, 1):
            # Use `user.timezone` (already in hand from the caller) rather than
            # the lazy-loaded `t.user` relationship, which would trigger a
            # DetachedInstanceError once we leave this session block anyway.
            due_note = f" (due {format_for_whatsapp(t.due_date, user.timezone)})" if t.due_date else ""
            lines.append(f"{i}. {t.text}{due_note}")
        return "\n".join(lines)


def handle_complete_todo(intent: dict, user) -> str:
    text_hint = intent["text_hint"].lower()

    with get_session() as session:
        matches = (
            session.query(Todo)
            .filter(
                Todo.user_id == user.id,
                Todo.status == "open",
                Todo.text.ilike(f"%{text_hint}%"),
            )
            .all()
        )

        if not matches:
            return f"I couldn't find an open to-do matching \"{intent['text_hint']}\"."

        if len(matches) > 1:
            lines = ["I found a few matches — which one did you mean?"]
            for m in matches:
                lines.append(f"• {m.text}")
            return "\n".join(lines)

        todo = matches[0]
        todo.status = "done"
        session.commit()
        return f"✅ Marked \"{todo.text}\" as done. Nice work."
