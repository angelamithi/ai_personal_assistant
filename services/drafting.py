"""
Drafting service: turns a rough context/intent into a ready-to-copy
message or email draft, sent back to the user in WhatsApp as plain text.

No sending capability on purpose — the user has more than one outbound
email address (Gmail + a GoDaddy-hosted professional address) and prefers
to pick which one and hit send themselves, so this only ever returns text.
"""
import os

from anthropic import Anthropic

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def draft_email(context: str, recipient_hint: str | None, tone: str | None) -> str:
    system_prompt = (
        "You write clear, professional email drafts on request. Output ONLY the "
        "email, formatted as:\nSubject: <subject line>\n\n<body>\n\nNo preamble, "
        "no markdown, no commentary before or after — the user will copy this "
        "directly into their email client."
    )
    user_prompt = f"Context: {context}"
    if recipient_hint:
        user_prompt += f"\nRecipient: {recipient_hint}"
    if tone:
        user_prompt += f"\nDesired tone: {tone}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=600,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()


def draft_message(context: str, recipient_hint: str | None, tone: str | None) -> str:
    system_prompt = (
        "You write short, natural-sounding chat/text messages on request "
        "(WhatsApp, SMS, Slack style — not formal email). Output ONLY the "
        "message text itself, no preamble, no quotation marks around it, "
        "no commentary — the user will copy this directly."
    )
    user_prompt = f"Context: {context}"
    if recipient_hint:
        user_prompt += f"\nRecipient: {recipient_hint}"
    if tone:
        user_prompt += f"\nDesired tone: {tone}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text.strip()
