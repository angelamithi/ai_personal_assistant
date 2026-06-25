# AI Personal Assistant (WhatsApp)

A Memorae-style personal assistant that lives inside WhatsApp. Handles:

- Calendar events (internal DB, no Google sync)
- One-off and recurring reminders
- To-do lists
- Voice notes (transcribed via OpenAI's Whisper endpoint)
- Drafting messages/emails (returned in-chat, you copy-paste and send yourself)
- Daily morning briefing (today's events + open to-dos)
- Event reminder nudges before they start

This is a **separate project** from `ai-social-agent`. It uses its own:
- WhatsApp test number / Meta App
- Postgres database (`assistant-db`)
- Render web service (`assistant-webhook`)

It does **not** share infrastructure with the social-posting agent, by design — different product, different scaling/debugging needs.

## Setup — start here

This README covers architecture only. For actual step-by-step setup:

1. **Test locally first** → see `TESTING.md` (run the server on your machine, fake WhatsApp messages with curl, confirm the logic works before touching Meta or Render at all)
2. **Deploy for real** → see `render.md` (covers creating the Postgres database, the Render web service, setting all environment variables, and wiring up the actual Meta/WhatsApp webhook — in that order, since each step depends on values from the one before it)

Skipping straight to `render.md` is fine too if you'd rather test against the live deployment from the start.

## How it works

1. WhatsApp message (text or voice) hits `POST /webhook` in `webhook_server.py`.
2. Voice notes: media is downloaded from Meta, transcribed via OpenAI Whisper, converted to text.
3. Text is sent to Claude with a system prompt that classifies intent and extracts structured fields (`services/intent_parser.py`).
4. The matching handler in `routes/` reads/writes Postgres and replies via WhatsApp.
5. A background scheduler thread (`services/scheduler.py`, using APScheduler) runs every minute inside the same web process and:
   - Sends due reminders (and reschedules recurring ones)
   - Sends "starting soon" nudges for events
   - Sends each user's daily briefing at their configured time

No second Render service is needed for the scheduler — it runs as a background thread in the same always-on web service, to avoid paying for an extra Starter instance.

## Local setup

```bash
cp .env.example .env
# fill in your values
pip install -r requirements.txt
uvicorn webhook_server:app --reload --port 8000
```

Use `ngrok http 8000` (or similar) to get a public URL for Meta's webhook verification while testing locally.

## Deploying to Render

See `DEPLOY.md` for the full manual walkthrough (Postgres instance, Web Service, environment variables, Meta webhook callback URL).

## Project layout

```
ai-personal-assistant/
├── webhook_server.py        # FastAPI app, /webhook route, starts scheduler on boot
├── database.py               # SQLAlchemy engine/session setup
├── models/
│   └── models.py              # User, Event, Reminder, Todo, ConversationState
├── services/
│   ├── whatsapp_client.py     # send_text_message, send_template, download_media
│   ├── transcription.py       # OpenAI Whisper call
│   ├── intent_parser.py       # Claude call -> structured intent JSON
│   ├── drafting.py            # Claude call -> drafted message/email text
│   └── scheduler.py           # APScheduler jobs: reminders, event nudges, briefing
├── routes/
│   ├── events.py              # create/list/update/cancel event handlers
│   ├── reminders.py           # create/list/complete reminder handlers
│   └── todos.py                # create/list/complete/delete todo handlers
├── utils/
│   └── datetime_parsing.py    # natural language -> datetime helpers, timezone handling
├── scripts/
│   └── init_db.py              # creates tables on first deploy
├── requirements.txt
├── .env.example
├── render.md                  # manual Render setup steps (no render.yaml, per your last project's preference)
└── README.md
```
