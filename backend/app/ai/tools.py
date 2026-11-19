"""Tools the LLM may request. The LLM never touches the database directly.

Every call is validated with Pydantic and executed by backend services.

- Information tools return data to the model, which then phrases the answer.
- Action tools are terminal: the backend runs them and writes the reply itself, so Ava can never
  claim a booking, cancellation or handoff that did not happen.
- Booking, rescheduling and cancelling never happen in the same turn as the request. The tool
  stores a *pending action* with a summary; the customer must answer "yes" in their next message
  (see chat_service), and only then is the action executed.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time
from datetime import date as Date, time as Time

from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from ..models import AvaConversation
from ..services import appointment_service as appts
from ..services import business_service, faq_service, lead_service
from ..services.appointment_service import AppointmentError
from ..services.lead_service import LeadError
from ..services.validation import (
    clean_text,
    is_valid_email,
    is_valid_name,
    is_valid_phone,
    normalize_phone,
)
from .chat_types import load_state, save_state

# ---------------------------------------------------------------------------
# Argument models
# ---------------------------------------------------------------------------


class _Args(BaseModel):
    model_config = {"extra": "ignore", "str_strip_whitespace": True}


class NoArgs(_Args):
    pass


class SearchFaqArgs(_Args):
    query: str = Field(min_length=2, max_length=300)


class CheckAvailabilityArgs(_Args):
    date: Date | None = None


def _check_phone(value: str) -> str:
    if not is_valid_phone(value):
        raise ValueError("phone number must have 10-15 digits")
    return value


class BookArgs(_Args):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(max_length=30)
    service: str = Field(min_length=2, max_length=255)
    date: Date
    time: Time
    email: str | None = None

    _phone = field_validator("phone")(_check_phone)

    @field_validator("name")
    @classmethod
    def _name(cls, v):
        if not is_valid_name(v):
            raise ValueError("a real full name is required")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        if v and not is_valid_email(v):
            raise ValueError("e-mail address is not valid")
        return v or None


class RescheduleArgs(_Args):
    booking_code: str = Field(min_length=4, max_length=16)
    phone: str = Field(max_length=30)
    new_date: Date
    new_time: Time

    _phone = field_validator("phone")(_check_phone)


class CancelArgs(_Args):
    booking_code: str = Field(min_length=4, max_length=16)
    phone: str = Field(max_length=30)
    reason: str | None = Field(default=None, max_length=500)

    _phone = field_validator("phone")(_check_phone)


class LeadArgs(_Args):
    name: str = Field(min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    service: str | None = Field(default=None, max_length=255)
    preferred_datetime: str | None = Field(default=None, max_length=100)
    message: str | None = Field(default=None, max_length=2000)


class HandoffArgs(_Args):
    reason: str = Field(min_length=2, max_length=2000)
    name: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=255)


FIELD_LABELS = {
    "name": "your full name", "phone": "your phone number", "service": "the service you want",
    "date": "the date", "time": "the time", "new_date": "the new date", "new_time": "the new time",
    "booking_code": "your booking code", "email": "a valid e-mail address", "reason": "the reason",
    "query": "your question",
}

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI-style JSON schema, understood by Qwen's chat template)
# ---------------------------------------------------------------------------


def _fn(name, description, properties=None, required=None):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []},
    }}


_S = {"type": "string"}
TOOL_DEFINITIONS = [
    _fn("get_business_information", "Business name, description, phone, e-mail, address, website."),
    _fn("search_faq", "Search the business FAQ for an answer.", {"query": _S}, ["query"]),
    _fn("get_services", "List services with prices and durations."),
    _fn("get_business_hours", "Opening hours for each weekday."),
    _fn("check_availability", "Show free appointment dates, or free times on one date (YYYY-MM-DD).",
        {"date": _S}),
    _fn("book_appointment", "Prepare a booking. Call only when you have name, phone, service, date and time.",
        {"name": _S, "phone": _S, "service": _S, "date": {"type": "string", "description": "YYYY-MM-DD"},
         "time": {"type": "string", "description": "HH:MM 24h"}, "email": _S},
        ["name", "phone", "service", "date", "time"]),
    _fn("reschedule_appointment", "Prepare moving an existing booking. Needs booking code and phone.",
        {"booking_code": _S, "phone": _S, "new_date": _S, "new_time": _S},
        ["booking_code", "phone", "new_date", "new_time"]),
    _fn("cancel_appointment", "Prepare cancelling an existing booking. Needs booking code and phone.",
        {"booking_code": _S, "phone": _S, "reason": _S}, ["booking_code", "phone"]),
    _fn("create_customer_lead", "Save contact details so the team can follow up (quote, callback).",
        {"name": _S, "phone": _S, "email": _S, "service": _S, "preferred_datetime": _S, "message": _S},
        ["name"]),
    _fn("request_human_handoff", "Ask a human team member to take over.",
        {"reason": _S, "name": _S, "phone": _S, "email": _S}, ["reason"]),
]

INFO_TOOLS = {"get_business_information", "search_faq", "get_services", "get_business_hours"}
ACTION_TOOLS = {"check_availability", "book_appointment", "reschedule_appointment", "cancel_appointment",
                "create_customer_lead", "request_human_handoff"}

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


@dataclass
class ToolContext:
    db: Session
    conversation: AvaConversation
    now: datetime
    events: list[str] = field(default_factory=list)


@dataclass
class ToolOutcome:
    """`data` goes back to the model (info tools). `reply` ends the turn (action tools)."""

    data: dict | None = None
    reply: str | None = None
    ui_action: str | None = None
    ui_data: dict | None = None


def _missing_fields_message(exc: ValidationError, action: str) -> str:
    fields = []
    for err in exc.errors():
        name = str(err["loc"][0]) if err.get("loc") else ""
        label = FIELD_LABELS.get(name, name)
        if label and label not in fields:
            fields.append(label)
    return f"To {action}, I still need {', '.join(fields)}." if fields else f"I need a few more details to {action}."


def _when(d: date, t: time) -> str:
    return datetime.combine(d, t).strftime("%A, %d %b %Y at %I:%M %p")


def _set_pending(ctx: ToolContext, kind: str, args: dict) -> None:
    state = load_state(ctx.conversation)
    state["pending_action"] = {"type": kind, "args": args}
    save_state(ctx.conversation, state)


def execute_tool(ctx: ToolContext, name: str, arguments: dict) -> ToolOutcome:
    db = ctx.db
    try:
        # ---- information -------------------------------------------------
        if name == "get_business_information":
            return ToolOutcome(data=business_service.get_business_information(db))
        if name == "get_services":
            return ToolOutcome(data={"services": business_service.get_services(db)})
        if name == "get_business_hours":
            return ToolOutcome(data={"hours": business_service.get_business_hours(db)})
        if name == "search_faq":
            args = SearchFaqArgs(**arguments)
            hits = [h for h in faq_service.search_faq(db, args.query, limit=3) if h["score"] > 0.05]
            return ToolOutcome(data={"results": [{"question": h["question"], "answer": h["answer"]} for h in hits]})

        # ---- availability ------------------------------------------------
        if name == "check_availability":
            args = CheckAvailabilityArgs(**arguments)
            if args.date:
                slots = appts.available_slots(db, args.date, ctx.now)
                if not any(s["available"] for s in slots):
                    dates = appts.available_dates(db, ctx.now)
                    return ToolOutcome(reply=f"Sorry, there are no free times on {args.date.strftime('%A, %d %b')}."
                                       " Please choose another date:", ui_action="select_date",
                                       ui_data={"dates": dates})
                return ToolOutcome(reply=f"Here are the free times on {args.date.strftime('%A, %d %b %Y')}:",
                                   ui_action="select_time", ui_data={"date": args.date.isoformat(), "slots": slots})
            dates = appts.available_dates(db, ctx.now)
            if not any(not d["disabled"] for d in dates):
                return ToolOutcome(reply="Sorry, there are no free appointments in the current booking window. "
                                         "Would you like our team to contact you?")
            return ToolOutcome(reply="Here are the dates with free appointments. Please pick one:",
                               ui_action="select_date", ui_data={"dates": dates})

        # ---- actions that need confirmation ------------------------------
        if name == "book_appointment":
            try:
                args = BookArgs(**arguments)
            except ValidationError as exc:
                return ToolOutcome(reply=_missing_fields_message(exc, "book your appointment"))
            try:
                appts.validate_slot(db, args.date, args.time, now=ctx.now)
            except AppointmentError as exc:
                return _slot_problem(ctx, exc, args.date)
            _set_pending(ctx, "book", {
                "name": clean_text(args.name, 100), "phone": args.phone, "email": args.email,
                "service": clean_text(args.service, 255), "date": args.date.isoformat(),
                "time": args.time.strftime("%H:%M"),
            })
            return ToolOutcome(reply=(
                "Please confirm your appointment details:\n\n"
                f"Name: {args.name}\nPhone: {args.phone}\nService: {args.service}\n"
                f"Date & time: {_when(args.date, args.time)}\n\nReply yes to confirm or no to cancel."
            ))

        if name == "reschedule_appointment":
            try:
                args = RescheduleArgs(**arguments)
            except ValidationError as exc:
                return ToolOutcome(reply=_missing_fields_message(exc, "reschedule"))
            appointment = appts.find_customer_appointment(db, args.booking_code, args.phone)
            appts.validate_slot(db, args.new_date, args.new_time, now=ctx.now, exclude_appointment_id=appointment.id)
            _set_pending(ctx, "reschedule", {
                "appointment_id": appointment.id, "booking_code": appointment.booking_code,
                "phone": normalize_phone(args.phone), "date": args.new_date.isoformat(),
                "time": args.new_time.strftime("%H:%M"),
            })
            return ToolOutcome(reply=(
                f"Please confirm: move booking {appointment.booking_code} "
                f"({appointment.appointment_date.strftime('%A, %d %b at %I:%M %p')}) to "
                f"{_when(args.new_date, args.new_time)}?\n\nReply yes to confirm or no to keep the current time."
            ))

        if name == "cancel_appointment":
            try:
                args = CancelArgs(**arguments)
            except ValidationError as exc:
                return ToolOutcome(reply=_missing_fields_message(exc, "cancel"))
            appointment = appts.find_customer_appointment(db, args.booking_code, args.phone)
            if appointment.status not in ("pending", "confirmed") or appointment.appointment_date <= ctx.now:
                return ToolOutcome(reply=f"This appointment is {appointment.status} or already in the past, so it "
                                         "can't be cancelled online.")
            _set_pending(ctx, "cancel", {"appointment_id": appointment.id, "booking_code": appointment.booking_code,
                                         "phone": normalize_phone(args.phone), "reason": args.reason})
            return ToolOutcome(reply=(
                f"Please confirm: cancel your {appointment.service} appointment on "
                f"{appointment.appointment_date.strftime('%A, %d %b %Y at %I:%M %p')} "
                f"(booking {appointment.booking_code})?\n\nReply yes to cancel or no to keep it."
            ))

        # ---- actions without confirmation --------------------------------
        if name == "create_customer_lead":
            try:
                args = LeadArgs(**arguments)
            except ValidationError as exc:
                return ToolOutcome(reply=_missing_fields_message(exc, "save your details"))
            try:
                lead = lead_service.create_lead(
                    db, name=args.name, phone=args.phone, email=args.email, service=args.service,
                    preferred_datetime=args.preferred_datetime, message=args.message,
                    conversation_id=ctx.conversation.id,
                )
            except LeadError as exc:
                return ToolOutcome(reply=exc.message)
            ctx.conversation.customer_id = lead.customer_id or ctx.conversation.customer_id
            ctx.events.append("lead_created")
            return ToolOutcome(reply=f"Thank you, {lead.name}. I've saved your details and our team will get back "
                                     "to you.")

        if name == "request_human_handoff":
            try:
                args = HandoffArgs(**arguments)
            except ValidationError:
                args = HandoffArgs(reason="Customer asked for a person.")
            _, created = lead_service.request_handoff(
                db, ctx.conversation, reason=args.reason, name=args.name, phone=args.phone, email=args.email,
            )
            ctx.events.append("handoff_requested" if created else "handoff_updated")
            has_contact = bool(args.phone or args.email)
            return ToolOutcome(reply=(
                "I've asked a member of our team to help you. Nobody has replied yet; they will get back to you "
                "as soon as possible."
                + ("" if has_contact else " If you share your name and phone number, they can contact you directly.")
            ))

        return ToolOutcome(data={"error": f"Unknown tool '{name}'."})

    except ValidationError as exc:
        return ToolOutcome(data={"error": "Invalid arguments", "details": exc.errors(include_url=False)[:3]})
    except AppointmentError as exc:
        return ToolOutcome(reply=exc.message)


def _slot_problem(ctx: ToolContext, exc: AppointmentError, day: date) -> ToolOutcome:
    if exc.code in {"slot_taken", "past", "invalid_slot", "outside_hours"}:
        slots = appts.available_slots(ctx.db, day, ctx.now)
        if any(s["available"] for s in slots):
            return ToolOutcome(reply=f"{exc.message} These times are free on {day.strftime('%A, %d %b')}:",
                               ui_action="select_time", ui_data={"date": day.isoformat(), "slots": slots})
    return ToolOutcome(reply=f"{exc.message} Please choose another date:", ui_action="select_date",
                       ui_data={"dates": appts.available_dates(ctx.db, ctx.now)})


# ---------------------------------------------------------------------------
# Confirmed actions (run by chat_service when the customer answers "yes")
# ---------------------------------------------------------------------------


def run_pending_action(ctx: ToolContext, pending: dict) -> str:
    """Executes a confirmed pending action. Raises AppointmentError on rule violations."""
    db, args, kind = ctx.db, pending.get("args", {}), pending.get("type")
    if kind == "book":
        appointment = appts.book_appointment(
            db, name=args["name"], phone=args["phone"], email=args.get("email"), service=args["service"],
            day=date.fromisoformat(args["date"]), start=time.fromisoformat(args["time"]),
            source="website_chat", actor="ava", conversation_id=ctx.conversation.id, now=ctx.now, commit=False,
        )
        ctx.conversation.customer_id = appointment.customer_id or ctx.conversation.customer_id
        ctx.events.append("appointment_booked")
        return (
            f"Your appointment request has been submitted, {appointment.name}!\n\n"
            f"Booking code: {appointment.booking_code}\nService: {appointment.service}\n"
            f"Date & time: {appointment.appointment_date.strftime('%A, %d %b %Y at %I:%M %p')}\n\n"
            "It is pending confirmation by our team. Keep your booking code: you need it, with your phone "
            "number, to reschedule or cancel."
        )

    appointment = appts.find_customer_appointment(db, args.get("booking_code", ""), args.get("phone", ""))
    if appointment.id != args.get("appointment_id"):
        raise AppointmentError("not_found", "I could not find that appointment any more.")
    if kind == "reschedule":
        appts.reschedule_appointment(db, appointment, date.fromisoformat(args["date"]),
                                     time.fromisoformat(args["time"]), actor="customer", now=ctx.now, commit=False)
        ctx.events.append("appointment_rescheduled")
        return (f"Done! Booking {appointment.booking_code} is now on "
                f"{appointment.appointment_date.strftime('%A, %d %b %Y at %I:%M %p')}.")
    if kind == "cancel":
        appts.cancel_appointment(db, appointment, actor="customer", reason=args.get("reason") or "Cancelled via chat",
                                 now=ctx.now, commit=False)
        ctx.events.append("appointment_cancelled")
        return f"Your appointment {appointment.booking_code} has been cancelled."
    raise AppointmentError("unknown_action", "There is nothing to confirm.")

