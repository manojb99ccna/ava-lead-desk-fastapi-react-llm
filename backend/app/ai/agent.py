"""LLM-driven Ava: builds the prompt, runs the tool-calling loop and guards the final reply."""
import json
import logging
import re
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from ..core.config import settings
from ..models import AvaAppointment, AvaConversation, AvaMessage
from ..services import business_service, faq_service
from .llm_client import LLMClient, LLMUnavailable
from .tools import ACTION_TOOLS, TOOL_DEFINITIONS, ToolContext, execute_tool
from .chat_types import ChatResult, load_state

logger = logging.getLogger("ava.agent")

_CLAIM_RE = re.compile(
    r"\b(is|are|has been|have been|been|now|successfully)\s+(booked|scheduled|confirmed|cancel+ed|rescheduled)\b",
    re.IGNORECASE,
)
_CODE_RE = re.compile(r"\bAVA-[A-Z0-9]{4,8}\b")


def _facts(db: Session, user_message: str) -> str:
    info = business_service.get_business_information(db)
    lines = []
    if info["description"]:
        lines.append(f"About: {info['description']}")
    contact = ", ".join(f"{k}: {info[k]}" for k in ("phone", "email", "address", "website") if info[k])
    if contact:
        lines.append(f"Contact: {contact}")
    lines.append("Opening hours: " + "; ".join(
        f"{h['day'][:3]} {h['opening_time']}-{h['closing_time']}" if h["is_open"] else f"{h['day'][:3]} closed"
        for h in business_service.get_business_hours(db)
    ))
    services = business_service.get_services(db)
    if services:
        lines.append("Services: " + "; ".join(
            s["name"] + (f" ({s['price']})" if s["price"] else "") for s in services
        ))
    hits = [h for h in faq_service.search_faq(db, user_message, limit=2) if h["score"] >= 0.15]
    for h in hits:
        lines.append(f"FAQ: Q: {h['question']} A: {h['answer']}")
    return "\n".join(lines)


def build_system_prompt(db: Session, conversation: AvaConversation, user_message: str, now: datetime) -> str:
    s = business_service.get_settings(db)
    name = s.business_name or "the business"
    state = load_state(conversation)
    chosen = f"\nThe customer picked the date {state['llm_selected_date']}." if state.get("llm_selected_date") else ""
    # Small models are poor at date arithmetic, so spell out the coming week.
    calendar = ", ".join(
        f"{(now + timedelta(days=i)).strftime('%A')}={(now + timedelta(days=i)).date().isoformat()}"
        + (" (today)" if i == 0 else " (tomorrow)" if i == 1 else "")
        for i in range(8)
    )
    return (
        f"You are Ava, the friendly AI receptionist of {name}. "
        f"Now: {now.strftime('%A %Y-%m-%d %H:%M')} ({s.timezone}).{chosen}\n"
        f"Dates: {calendar}\n"
        f"Verified facts:\n{_facts(db, user_message)}\n"
        "Rules:\n"
        "- Use only the facts above or tool results. Never invent prices, services, times or policies. "
        "If you don't know, say so and offer request_human_handoff.\n"
        "- Booking: get full name, phone, service, date and time. Use check_availability to show free "
        "dates or times. Call book_appointment only when you have all five.\n"
        "- Reschedule or cancel: ask for the booking code and phone number, then call the tool.\n"
        "- Call request_human_handoff if the customer wants a person or you cannot help.\n"
        "- Reply in 1-3 short sentences, in the customer's language. Ask one question at a time."
    )


def _history(db: Session, conversation: AvaConversation) -> list[dict]:
    limit = max(0, settings.llm_history_messages)
    if not limit or not conversation.id:
        return []
    rows = (
        db.query(AvaMessage)
        .filter(AvaMessage.conversation_id == conversation.id)
        .order_by(AvaMessage.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {"role": "user" if m.sender == "user" else "assistant", "content": m.message[:1500]}
        for m in reversed(rows)
    ]


def _guard(db: Session, text: str) -> str:
    """Stops the model from claiming actions or booking codes that the backend did not produce."""
    if _CLAIM_RE.search(text):
        logger.warning("LLM claimed an action without a tool result; reply replaced.")
        return ("I haven't booked or changed anything yet. Would you like me to check the available "
                "appointment times?")
    for code in set(_CODE_RE.findall(text)):
        if not db.query(AvaAppointment.id).filter(AvaAppointment.booking_code == code).first():
            logger.warning("LLM mentioned an unknown booking code; reply replaced.")
            return "Sorry, I made a mistake there. Could you tell me again what you would like to do?"
    return text


def run(db: Session, client: LLMClient, conversation: AvaConversation, user_message: str,
        now: datetime) -> ChatResult:
    messages = [
        {"role": "system", "content": build_system_prompt(db, conversation, user_message, now)},
        *_history(db, conversation),
        {"role": "user", "content": user_message},
    ]
    ctx = ToolContext(db=db, conversation=conversation, now=now)

    for _ in range(max(1, settings.llm_max_tool_rounds)):
        reply = client.complete(messages, TOOL_DEFINITIONS)

        if not reply.tool_calls:
            text = (reply.content or "").strip()
            if not text:
                raise LLMUnavailable("Empty reply from LLM")
            return ChatResult(_guard(db, text), engine="llm", events=ctx.events)

        messages.append(reply.as_message())
        for call in reply.tool_calls:
            if call.name == "__invalid__":
                result = {"error": "Your tool call was not valid JSON. Try again or answer directly."}
            else:
                outcome = execute_tool(ctx, call.name, call.arguments)
                if outcome.reply is not None and call.name in ACTION_TOOLS:
                    return ChatResult(outcome.reply, outcome.ui_action, outcome.ui_data, engine="llm",
                                      events=ctx.events)
                result = outcome.data if outcome.data is not None else {"result": outcome.reply}
            messages.append({"role": "tool", "name": call.name, "content": json.dumps(result, default=str)[:4000]})

    raise LLMUnavailable("Too many tool rounds")
