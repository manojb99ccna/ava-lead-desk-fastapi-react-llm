"""Input validation helpers shared by the chat engines, tools and API routes."""
import re

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_CODE_RE = re.compile(r"^AVA-[A-Z0-9]{6}$")

_NOT_A_NAME = {
    "yes", "no", "yeah", "nope", "mistake", "wait", "ok", "okay", "cancel", "stop",
    "tell me about yourself", "who are you", "what do you do", "hi", "hello", "hey", "help",
}
_QUESTION_WORDS = {"tell", "about", "yourself", "what", "who", "how", "why", "where", "can", "do"}


def normalize_phone(phone: str | None) -> str:
    """Keeps digits only (a leading + is dropped). Used for matching and storage keys."""
    return re.sub(r"\D", "", phone or "")


def is_valid_phone(phone: str | None) -> bool:
    return 10 <= len(normalize_phone(phone)) <= 15


def is_valid_email(email: str | None) -> bool:
    return bool(email) and len(email) <= 255 and bool(_EMAIL_RE.match(email.strip()))


def is_valid_name(name: str | None) -> bool:
    if not name:
        return False
    name_clean = name.strip()
    name_lower = name_clean.lower()

    if len(name_clean) < 2 or len(name_clean) > 40:
        return False
    if name_lower in _NOT_A_NAME:
        return False

    words = name_clean.split()
    if len(words) > 4:
        return False
    if len(words) > 1 and any(word in _QUESTION_WORDS for word in name_lower.split()):
        return False
    if any(char.isdigit() for char in name_clean):
        return False
    return True


def is_valid_datetime_text(dt_str: str | None) -> bool:
    """Loose check for a free-text preferred date/time such as 'Tomorrow at 2 PM'."""
    dt_clean = (dt_str or "").strip().lower()
    if dt_clean in {"no", "cancel", "stop", "nope", "skip", "none"} or len(dt_clean) < 3:
        return False
    keywords = [
        "tomorrow", "today", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday",
        "sunday", "am", "pm", "morning", "afternoon", "evening", "night", "now", "soon", "at", ":",
    ]
    return any(c.isdigit() for c in dt_clean) or any(k in dt_clean for k in keywords) or len(dt_clean) >= 5


def normalize_booking_code(code: str | None) -> str:
    """Accepts 'AVA-7K3P9Q', 'ava 7k3p9q', 'AVA7K3P9Q' or just '7K3P9Q'."""
    code = re.sub(r"[\s-]", "", (code or "").strip().upper())
    if code.startswith("AVA") and len(code) == 9:
        code = code[3:]
    return f"AVA-{code}" if re.fullmatch(r"[A-Z0-9]{6}", code) else ""


def is_valid_booking_code(code: str | None) -> bool:
    return bool(_CODE_RE.match(normalize_booking_code(code)))


def clean_text(value: str | None, max_length: int) -> str | None:
    if value is None:
        return None
    value = " ".join(str(value).split())
    return value[:max_length] if value else None
