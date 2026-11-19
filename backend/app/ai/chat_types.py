import json
from dataclasses import dataclass, field
from datetime import date, time


@dataclass
class ChatTurn:
    message: str
    action: str | None = None
    selected_date: date | None = None
    selected_time: time | None = None


@dataclass
class ChatResult:
    reply: str
    ui_action: str | None = None
    data: dict | None = None
    engine: str = "rules"
    events: list[str] = field(default_factory=list)  # e.g. "appointment_booked", "handoff_requested"


def load_state(conversation) -> dict:
    try:
        return json.loads(conversation.lead_data) if conversation.lead_data else {}
    except (TypeError, ValueError):
        return {}


def save_state(conversation, state: dict) -> None:
    conversation.lead_data = json.dumps(state, default=str)
