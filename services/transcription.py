"""
Voice note transcription.

Uses the SAME OpenAI API key as everything else on your account — Whisper
is just the audio endpoint of the OpenAI API, not a separate product or
signup. See README for the full explanation if this looks unfamiliar.
"""
import io
import os

from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def transcribe_audio(audio_bytes: bytes, filename: str = "voice_note.ogg") -> str:
    """
    Transcribe WhatsApp voice note audio (typically OGG/Opus) to text.

    WhatsApp voice notes are usually .ogg containers, which Whisper
    supports natively, so no conversion step is needed.
    """
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename  # the SDK reads this to infer format

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=audio_file,
    )
    return transcript.text.strip()
