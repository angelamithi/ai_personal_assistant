# Local Testing (before connecting Meta)

Sanity-check the webhook on your machine first, with fake payloads, before
touching real Meta/WhatsApp setup. Saves you a round trip every time you
want to check a code change.

## 1. Start the server locally

```bash
cp .env.example .env
# Fill in a REAL ANTHROPIC_API_KEY — every message goes through Claude for
# intent parsing FIRST, before anything else happens, so a dummy key here
# makes every single test request fail with a 500 error (Anthropic 401).
# A real OPENAI_API_KEY is only needed once you test voice notes (step 6).
# DATABASE_URL can point at a local Postgres, or use SQLite for quick testing:
#   DATABASE_URL=sqlite:///test_assistant.db

pip install -r requirements.txt --break-system-packages
python scripts/init_db.py
uvicorn webhook_server:app --reload --port 8000
```

WhatsApp creds (`WHATSAPP_*`) CAN stay as dummy values. The flow is:
incoming message → Claude parses intent → handler writes to DB → THEN it
tries to send the WhatsApp reply. So with a real Anthropic key but dummy
WhatsApp creds, the DB write succeeds and you'll see a clean error only at
the final send step — confirm via step 5 below that the row actually landed.

## 2. Verify the webhook handshake

```bash
curl "http://localhost:8000/webhook?hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=12345"
```
Expect: `12345` back, status 200. Wrong token → 403.

## 3. Send a fake text message

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "changes": [{
        "value": {
          "messages": [{
            "from": "254700000000",
            "type": "text",
            "text": { "body": "remind me tomorrow at 9am to call the dentist" }
          }]
        }
      }]
    }]
  }'
```
Expect a 500 "Internal Server Error" in the curl response if `WHATSAPP_*`
creds are dummy — that's just the WhatsApp send failing at the very last
step, AFTER your reminder/event/todo was already written to the DB. The
error response looks alarming but the data already saved correctly; verify
with step 5 below rather than trusting the HTTP response here.

If `ANTHROPIC_API_KEY` is also a dummy value, you'll get the same-looking
500 error, but for a different reason (intent parsing fails before anything
is saved) — check the server logs to tell which case you're in.

## 4. Try a few more intents

Swap the `"body"` text and re-run the same curl:

| Want to test | Message body |
|---|---|
| Create event | `"schedule a team meeting tomorrow at 3pm"` |
| List events | `"what's on my calendar today"` |
| To-do | `"add buy milk to my to do list"` |
| Complete to-do | `"mark buy milk as done"` |
| Draft email | `"draft an email to my landlord about the leaking tap"` |
| Multi-turn | `"remind me to call mom"` then, in a second curl, `"tomorrow at 6pm"` |

For the multi-turn case, run the two curls back to back — the second reply
should resolve into an actual reminder, not ask for clarification again.

## 5. Inspect what landed in the database

```bash
python3 -c "
from database import get_session
from models.models import User, Event, Reminder, Todo

with get_session() as session:
    for model in (User, Event, Reminder, Todo):
        print(f'--- {model.__name__} ---')
        for row in session.query(model).all():
            print(row.__dict__)
"
```

## 6. Test voice notes without a real audio file

Voice transcription needs a real `OPENAI_API_KEY` and an actual audio file,
so it's easiest to test this one with a real WhatsApp message once Meta is
wired up (see `render.md`), rather than faking it locally. Everything else
in this file can be fully checked before that point.

## 7. Reset between test runs

```bash
rm -f test_assistant.db
python scripts/init_db.py
```
(Skip this if you're using a real Postgres DB you want to keep.)

## When local testing looks good

Move to `render.md` to deploy for real and connect an actual WhatsApp number.
