import logging
import os
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


# Public settings
DISCORD_BOT_TOKEN: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")
GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY")


def get_gemini_model(model_name: str = "gemini-1.5-flash"):
    """
    Returns a configured Gemini model if google-generativeai is available and
    GEMINI_API_KEY is set. Otherwise returns None and logs the reason.
    """
    try:
        import google.generativeai as genai  # type: ignore
    except Exception:
        logging.warning(
            "google-generativeai not installed; disabling Gemini-powered features."
        )
        return None

    if not GEMINI_API_KEY:
        logging.warning("GEMINI_API_KEY not set; disabling Gemini-powered features.")
        return None

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        return genai.GenerativeModel(model_name)
    except Exception as e:
        logging.error(f"Failed to configure Gemini: {e}")
        return None

