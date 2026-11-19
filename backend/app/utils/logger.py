"""Debug file logging for the chat pipeline, plus redaction of personal data.

Chat debug logs are written only when CHAT_DEBUG_LOGS=true. Phone numbers, e-mail addresses and
booking codes are masked before anything is written.
"""
import logging
import os
import pprint
import re
from datetime import datetime

from app.core.config import settings

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_SENSITIVE_KEYS = {"phone", "email", "password", "token", "api_key", "booking_code", "authorization"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def redact_text(text: str) -> str:
    text = _EMAIL_RE.sub("[email]", text)
    return _PHONE_RE.sub("[phone]", text)


def redact(value):
    if isinstance(value, dict):
        return {
            k: ("[redacted]" if str(k).lower() in _SENSITIVE_KEYS and v else redact(v)) for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _logs_dir() -> str:
    backend_root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(backend_root_dir, "logs")


def log_debug_data(data_label: str, data_content, type: str = "info"):
    """Appends a readable, redacted debug block to backend/logs/. Errors are always written."""
    if type != "error" and not settings.chat_debug_logs:
        return

    filename = {
        "error": "debug_error_log.txt",
        "chat_faq": "debug_chat_faq_log.txt",
    }.get(type, "debug_chat_log.txt")

    try:
        logs_dir = _logs_dir()
        os.makedirs(logs_dir, exist_ok=True)
        content = redact(data_content)
        with open(os.path.join(logs_dir, filename), "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 50 + "\n")
            f.write(f"{datetime.now().isoformat(timespec='seconds')} | {data_label}\n")
            f.write("-" * 50 + "\n")
            if isinstance(content, (dict, list)):
                f.write(pprint.pformat(content, indent=4, width=100))
            else:
                f.write(str(content))
            f.write("\n" + "=" * 50 + "\n")
    except OSError:
        logging.getLogger("ava").exception("Could not write debug log")
