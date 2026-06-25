"""
Thin wrapper around Meta's WhatsApp Cloud API.

Two responsibilities:
1. Sending text replies back to the user.
2. Downloading voice note media so it can be transcribed.

Kept deliberately separate from ai-social-agent's WhatsApp client even
though the API calls look similar, since this project uses its own
WHATSAPP_PHONE_NUMBER_ID / WHATSAPP_ACCESS_TOKEN tied to a different
Meta App and test number.
"""
import os
import httpx

WHATSAPP_PHONE_NUMBER_ID = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
WHATSAPP_ACCESS_TOKEN = os.environ["WHATSAPP_ACCESS_TOKEN"]

GRAPH_API_BASE = "https://graph.facebook.com/v20.0"


async def send_text_message(to_phone_number: str, text: str) -> None:
    """Send a plain text WhatsApp message."""
    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone_number,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()


async def get_media_url(media_id: str) -> str:
    """Step 1 of downloading voice notes: resolve media_id to a temporary download URL."""
    url = f"{GRAPH_API_BASE}/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        return response.json()["url"]


async def download_media(media_url: str) -> bytes:
    """Step 2: download the actual audio bytes from the resolved URL."""
    headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.content
