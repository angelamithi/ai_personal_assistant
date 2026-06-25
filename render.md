# Deploying to Render (manual setup, no render.yaml)

Following the same approach as `ai-social-agent`: everything is clicked through
the dashboard rather than defined in a `render.yaml` blueprint, so you have full
visibility into each piece.

## 1. Create the Postgres database

1. Render Dashboard → **New +** → **PostgreSQL**.
2. Name it `assistant-db`.
3. Plan: **Free**.
4. Region: whichever is closest to you (doesn't need to match anything else).
5. Click **Create Database**.
6. Once provisioned, open it and copy the **Internal Database URL** — you'll
   paste this into the web service's environment variables in step 2.

## 2. Create the Web Service

1. **New +** → **Web Service**.
2. Connect your GitHub repo (`ai-personal-assistant`).
3. Name it `assistant-webhook`.
4. Runtime: **Python 3**.
5. Build Command:
   ```
   pip install -r requirements.txt
   ```
6. Start Command:
   ```
   uvicorn webhook_server:app --host 0.0.0.0 --port $PORT
   ```
7. Plan: **Starter** (~$7/mo) — needs to stay always-on so WhatsApp replies
   and the background scheduler (reminders, nudges, daily briefing) keep
   running continuously. The Free plan spins down on inactivity, which would
   silently break reminders.
8. Before clicking Create, scroll to **Environment Variables** and add every
   key from `.env.example` EXCEPT `WEBHOOK_PORT` (Render sets `$PORT` itself).
   Paste the Postgres Internal Database URL from step 1 into `DATABASE_URL`.
9. Click **Create Web Service** and wait for the first deploy to finish.

## 3. Run the DB init script once

Once deployed, open the service's **Shell** tab in the Render dashboard and run:
```bash
python scripts/init_db.py
```
This creates all tables. You only need to do this once (or again later if you
add new tables/columns and recreate them manually).

## 4. Set PUBLIC_BASE_URL

Now that the service is live, copy its real URL from the top of the service
page (something like `https://assistant-webhook-xxxx.onrender.com`) and paste
it into the `PUBLIC_BASE_URL` environment variable on this same service.

## 5. Set up the Meta webhook

1. Create a **new Meta App** (or a new test number within an existing app —
   your call) at developers.facebook.com, separate from the ai-social-agent
   app, so the two projects don't share a webhook destination.
2. Under WhatsApp → Configuration, set:
   - **Callback URL**: `https://assistant-webhook-xxxx.onrender.com/webhook`
   - **Verify Token**: must exactly match your `WHATSAPP_VERIFY_TOKEN` env var
3. Subscribe to the `messages` webhook field.
4. Add your real personal WhatsApp number as a verified recipient on the test
   number (Meta requires this in development mode, up to 5 numbers).

## 6. Test it

Message the test number from your verified personal number:
```
remind me tomorrow at 9am to call the dentist
```
You should get a confirmation back within a couple seconds, and the actual
reminder the next morning at 9am.

## Notes

- No second Render service is needed for the scheduler — it runs as a
  background thread inside `assistant-webhook` via APScheduler, started on
  FastAPI startup. This avoids paying for a second Starter instance just to
  check timestamps every minute.
- If you ever outgrow the free Postgres tier (storage/connection limits) or
  want migrations instead of `create_all()`, that's the natural next upgrade
  point — not needed for a single-user assistant at this scale.
