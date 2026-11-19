"""Rule-based Ava: ML intent detection, FAQ matching and step-by-step flows.

This is the original Ava behaviour, refactored onto the shared services. It runs when no LLM is
configured, and as a fallback when the LLM is unavailable.

Conversation state lives in ava_conversations.current_step and .lead_data (JSON).
"""
from datetime import date, datetime, time

from sqlalchemy.orm import Session

from ..models import AvaAppointment, AvaConversation, AvaHandoffRequest, AvaMessage
from ..services import appointment_service as appts
from ..services import business_service, faq_service, lead_service
from ..services.appointment_service import AppointmentError
from ..services.validation import (
    clean_text,
    is_valid_booking_code,
    is_valid_datetime_text,
    is_valid_name,
    is_valid_phone,
    normalize_booking_code,
)
from .intent import classify, predict_intent
from .chat_types import ChatResult, ChatTurn, load_state, save_state

RESET_WORDS = {"cancel", "stop", "start over", "restart", "never mind", "nevermind", "exit", "quit"}
YES_WORDS = {"yes", "y", "yeah", "yep", "confirm", "correct", "sure", "ok", "okay", "yes please", "confirmed"}
NO_WORDS = {"no", "n", "nope", "don't", "dont", "not now", "no thanks"}

BOOK_KEYWORDS = ["appointment", "schedule", "book", "meeting", "consultation"]
MANAGE_CANCEL = ["cancel my", "cancel the", "cancel an", "cancel appointment", "cancel booking"]
MANAGE_RESCHEDULE = ["reschedule", "change my appointment", "move my appointment", "change my booking",
                     "change the time", "different time"]
HANDOFF_KEYWORDS = ["human", "real person", "agent", "representative", "talk to someone",
                    "speak to someone", "speak with someone", "talk to a person", "staff member", "receptionist"]
LEAD_KEYWORDS = ["quote", "callback", "call back", "call me", "contact me", "get in touch", "estimate"]
NEGATIVE_PHRASES = ["don't want", "dont want", "do not want", "not interested", "no thanks", "no thank you",
                    "forget it", "leave it", "not now", "no need", "not needed", "nahi chahiye", "rehne do"]
BOOKING_OFFERS = ["book an appointment", "schedule a consultation", "book a consultation"]
# Intents that open a handoff request need a confident, non-trivial message.
HANDOFF_MIN_CONFIDENCE = 0.75
HANDOFF_MIN_WORDS = 3


def _is_negative(lower: str) -> bool:
    return lower in NO_WORDS or lower in RESET_WORDS or any(p in lower for p in NEGATIVE_PHRASES)


def _last_ava_message(db, conversation) -> str:
    row = (db.query(AvaMessage.message)
           .filter(AvaMessage.conversation_id == conversation.id, AvaMessage.sender == "ava")
           .order_by(AvaMessage.id.desc()).first())
    return row[0].lower() if row else ""


def _withdraw_incomplete_handoff(db, conversation) -> bool:
    """Withdraws the conversation's open handoff if it has no contact details yet."""
    handoff = (db.query(AvaHandoffRequest)
               .filter(AvaHandoffRequest.conversation_id == conversation.id, AvaHandoffRequest.status == "open")
               .order_by(AvaHandoffRequest.id.desc()).first())
    if not handoff or handoff.phone or handoff.email:
        return False
    handoff.status = "resolved"
    handoff.resolution_note = "Withdrawn by the customer in chat before giving contact details."
    conversation.status = "active"
    return True


def _reset(conversation: AvaConversation):
    conversation.current_step = None
    conversation.intent = None
    save_state(conversation, {})


def _norm(text: str) -> str:
    return " ".join(text.lower().strip(" .!?").split())


def _dates_result(db, reply, now, exclude_id=None) -> ChatResult:
    return ChatResult(reply, "select_date", {"dates": appts.available_dates(db, now, exclude_id)})


def _slots_result(db, reply, day: date, now, exclude_id=None) -> ChatResult:
    return ChatResult(
        reply, "select_time", {"date": day.isoformat(), "slots": appts.available_slots(db, day, now, exclude_id)}
    )


def _services_hint(db) -> str:
    names = [s["name"] for s in business_service.get_services(db)]
    return f" We offer: {', '.join(names)}." if names else ""


# ---------------------------------------------------------------------------
# Date / time pickers (booking and rescheduling share them)
# ---------------------------------------------------------------------------


def _handle_date(db, conversation, state, selected: date, now) -> ChatResult:
    exclude = state.get("appointment_id") if state.get("mode") == "reschedule" else None
    allowed = {d["date"] for d in appts.available_dates(db, now, exclude) if not d["disabled"]}
    if selected.isoformat() not in allowed:
        return _dates_result(db, "That date is not available. Please choose one of the available dates.", now, exclude)

    state["appointment_date"] = selected.isoformat()
    save_state(conversation, state)
    conversation.current_step = "booking_selecting_time"
    return _slots_result(
        db,
        f"Great! Here are the available times for {selected.strftime('%d %b %Y')}. Please select a time.",
        selected, now, exclude,
    )


def _handle_time(db, conversation, state, selected_date: date, selected_time: time, now) -> ChatResult:
    exclude = state.get("appointment_id") if state.get("mode") == "reschedule" else None
    if state.get("appointment_date") != selected_date.isoformat():
        conversation.current_step = "booking_selecting_date"
        return _dates_result(db, "Your selected date does not match. Please select the date again.", now, exclude)
    try:
        appts.validate_slot(db, selected_date, selected_time, now=now, exclude_appointment_id=exclude)
    except AppointmentError as exc:
        return _slots_result(db, f"{exc.message} Please select another time.", selected_date, now, exclude)

    state["appointment_time"] = selected_time.strftime("%H:%M")
    save_state(conversation, state)
    conversation.current_step = "booking_confirm"
    when = datetime.combine(selected_date, selected_time).strftime("%A, %d %b %Y at %I:%M %p")
    if state.get("mode") == "reschedule":
        return ChatResult(
            f"Please confirm: move booking {state['booking_code']} to {when}?\n\nReply yes to confirm or no to keep "
            "the current time."
        )
    return ChatResult(
        "Please confirm your appointment details:\n\n"
        f"Name: {state['name']}\nPhone: {state['phone']}\nService: {state['service']}\nDate & time: {when}\n\n"
        "Reply yes to confirm or no to cancel."
    )


def _handle_confirm(db, conversation, state, message, now) -> ChatResult:
    answer = _norm(message)
    if answer in NO_WORDS:
        _reset(conversation)
        return ChatResult("No problem, nothing has been changed. Is there anything else I can help you with?")
    if answer not in YES_WORDS:
        return ChatResult("Please reply yes to confirm, or no to cancel.")

    day = date.fromisoformat(state["appointment_date"])
    start = time.fromisoformat(state["appointment_time"])
    try:
        if state.get("mode") == "reschedule":
            appointment = db.get(AvaAppointment, state["appointment_id"])
            if not appointment:
                raise AppointmentError("not_found", "I could not find that appointment any more.")
            appts.reschedule_appointment(db, appointment, day, start, actor="customer", now=now, commit=False)
            _reset(conversation)
            return ChatResult(
                f"Done! Booking {appointment.booking_code} has been moved to "
                f"{appointment.appointment_date.strftime('%A, %d %b %Y at %I:%M %p')}.",
                events=["appointment_rescheduled"],
            )

        appointment = appts.book_appointment(
            db, name=state["name"], phone=state["phone"], service=state["service"], day=day, start=start,
            source="website_chat", actor="customer", conversation_id=conversation.id, now=now, commit=False,
        )
        conversation.customer_id = appointment.customer_id or conversation.customer_id
        _reset(conversation)
        return ChatResult(
            f"Your appointment request has been submitted, {appointment.name}!\n\n"
            f"Booking code: {appointment.booking_code}\nService: {appointment.service}\n"
            f"Date & time: {appointment.appointment_date.strftime('%A, %d %b %Y at %I:%M %p')}\n\n"
            "Your appointment is pending confirmation by our team. Please keep your booking code: you need it, "
            "with your phone number, to reschedule or cancel.",
            events=["appointment_booked"],
        )
    except AppointmentError as exc:
        if exc.code in {"slot_taken", "past", "invalid_slot"}:
            conversation.current_step = "booking_selecting_time"
            exclude = state.get("appointment_id") if state.get("mode") == "reschedule" else None
            return _slots_result(db, f"{exc.message} Please select another time.", day, now, exclude)
        _reset(conversation)
        return ChatResult(f"Sorry, that did not work: {exc.message}")


def _affirm(db, conversation) -> ChatResult:
    conversation.intent = "affirm"
    if any(offer in _last_ava_message(db, conversation) for offer in BOOKING_OFFERS):
        save_state(conversation, {"mode": "book"})
        conversation.current_step = "booking_collecting_name"
        return ChatResult("Great! Let's book your appointment. What is your full name?")
    return ChatResult("Great! What would you like to do? I can tell you about our services, prices and "
                      "opening hours, or book an appointment.")


def _decline(conversation) -> ChatResult:
    conversation.intent = "decline"
    return ChatResult("No problem! Is there anything else I can help you with?")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def handle(db: Session, conversation: AvaConversation, turn: ChatTurn, now: datetime | None = None) -> ChatResult:
    settings_row = business_service.get_settings(db)
    now = now or business_service.local_now(settings_row)
    state = load_state(conversation)
    step = conversation.current_step
    message = (turn.message or "").strip()
    lower = _norm(message)

    # Picker clicks
    if turn.action == "select_date":
        if step != "booking_selecting_date" or not turn.selected_date:
            return ChatResult("Please follow the appointment booking steps.")
        return _handle_date(db, conversation, state, turn.selected_date, now)
    if turn.action == "select_time":
        if step != "booking_selecting_time" or not (turn.selected_date and turn.selected_time):
            return ChatResult("Please follow the appointment booking steps.")
        return _handle_time(db, conversation, state, turn.selected_date, turn.selected_time, now)

    if not message:
        return ChatResult("Please enter a message.")

    # Leaving a flow ("no", "cancel", "I don't want ...") - except where "no" is the expected answer.
    if step and step not in {"booking_confirm", "manage_confirm_cancel"} and _is_negative(lower):
        withdrawn = step.startswith("handoff_") and _withdraw_incomplete_handoff(db, conversation)
        _reset(conversation)
        if withdrawn:
            return ChatResult("Okay, I've cancelled the request to our team, so nobody will contact you. "
                              "Is there anything else I can help you with?", events=["handoff_withdrawn"])
        return ChatResult("Okay, I've stopped that. How else can I help you?")

    # --- Appointment booking flow ----------------------------------------
    if step == "booking_collecting_name":
        if not is_valid_name(message):
            return ChatResult("That doesn't look like a valid name. Could you please provide your full name?")
        state["name"] = clean_text(message, 100)
        save_state(conversation, state)
        conversation.current_step = "booking_collecting_phone"
        return ChatResult(f"Thanks, {state['name']}! Now, could you please provide your phone number?")

    if step == "booking_collecting_phone":
        if not is_valid_phone(message):
            return ChatResult("That doesn't look like a valid phone number. Please enter a valid phone number.")
        state["phone"] = message.strip()
        save_state(conversation, state)
        conversation.current_step = "booking_collecting_service"
        return ChatResult("Great! Which service would you like to book?" + _services_hint(db))

    if step == "booking_collecting_service":
        if len(message) < 2 or len(message) > 255:
            return ChatResult("Please enter a valid service name.")
        state["service"] = clean_text(message, 255)
        save_state(conversation, state)
        dates = appts.available_dates(db, now)
        if not any(not d["disabled"] for d in dates):
            _reset(conversation)
            return ChatResult(
                "Sorry, there are no appointment times available in the current booking window. "
                "Would you like a member of our team to contact you instead?"
            )
        conversation.current_step = "booking_selecting_date"
        return ChatResult("Thank you! Please select an appointment date from the available dates below.",
                          "select_date", {"dates": dates})

    if step in {"booking_selecting_date", "booking_selecting_time"}:
        exclude = state.get("appointment_id") if state.get("mode") == "reschedule" else None
        if step == "booking_selecting_time" and state.get("appointment_date"):
            return _slots_result(db, "Please pick one of the times below, or type cancel to stop.",
                                 date.fromisoformat(state["appointment_date"]), now, exclude)
        return _dates_result(db, "Please pick one of the dates below, or type cancel to stop.", now, exclude)

    if step == "booking_confirm":
        return _handle_confirm(db, conversation, state, message, now)

    # --- Manage an existing booking --------------------------------------
    if step == "manage_collecting_code":
        if not is_valid_booking_code(message):
            return ChatResult("Please enter your booking code. It looks like AVA-7K3P9Q and is in your confirmation.")
        state["booking_code"] = normalize_booking_code(message)
        save_state(conversation, state)
        conversation.current_step = "manage_collecting_phone"
        return ChatResult("Thanks. What phone number did you use for the booking?")

    if step == "manage_collecting_phone":
        try:
            appointment = appts.find_customer_appointment(db, state.get("booking_code", ""), message)
        except AppointmentError as exc:
            _reset(conversation)
            return ChatResult(exc.message + " Please check the details and try again.")
        if appointment.status not in ("pending", "confirmed") or appointment.appointment_date <= now:
            _reset(conversation)
            return ChatResult(f"This appointment is {appointment.status} or already in the past, so it can't be "
                              "changed online. Would you like to speak with our team?")
        state["appointment_id"] = appointment.id
        when = appointment.appointment_date.strftime("%A, %d %b %Y at %I:%M %p")
        if state.get("mode") == "cancel":
            save_state(conversation, state)
            conversation.current_step = "manage_confirm_cancel"
            return ChatResult(f"I found your {appointment.service} appointment on {when}. "
                              "Do you want to cancel it? Reply yes or no.")
        state.update({"name": appointment.name, "phone": appointment.phone, "service": appointment.service})
        save_state(conversation, state)
        conversation.current_step = "booking_selecting_date"
        return _dates_result(db, f"I found your appointment on {when}. Please choose a new date.", now, appointment.id)

    if step == "manage_confirm_cancel":
        answer = _norm(message)
        if answer in NO_WORDS:
            _reset(conversation)
            return ChatResult("Okay, your appointment is unchanged.")
        if answer not in YES_WORDS:
            return ChatResult("Please reply yes to cancel the appointment, or no to keep it.")
        appointment = db.get(AvaAppointment, state.get("appointment_id"))
        _reset(conversation)
        try:
            if not appointment:
                raise AppointmentError("not_found", "I could not find that appointment any more.")
            appts.cancel_appointment(db, appointment, actor="customer", reason="Cancelled via chat", now=now,
                                     commit=False)
        except AppointmentError as exc:
            return ChatResult(f"Sorry, I could not cancel it: {exc.message}")
        return ChatResult(f"Your appointment {appointment.booking_code} has been cancelled.",
                          events=["appointment_cancelled"])

    # --- Lead capture flow -----------------------------------------------
    if step == "collecting_name":
        if not is_valid_name(message):
            return ChatResult("That doesn't look like a valid name. Could you please provide your full name?")
        state["name"] = clean_text(message, 100)
        save_state(conversation, state)
        conversation.current_step = "collecting_phone"
        return ChatResult(f"Thanks, {state['name']}! Could you please provide your phone number?")

    if step == "collecting_phone":
        if not is_valid_phone(message):
            return ChatResult("That doesn't look like a valid phone number. Please enter a valid phone number "
                              "so we can reach you.")
        state["phone"] = message.strip()
        save_state(conversation, state)
        conversation.current_step = "collecting_service"
        return ChatResult("Great! What service are you interested in?" + _services_hint(db))

    if step == "collecting_service":
        state["requested_service"] = clean_text(message, 255)
        save_state(conversation, state)
        conversation.current_step = "collecting_datetime"
        return ChatResult("When would you prefer we contact you or schedule a consultation? (e.g., Tomorrow at 2 PM)")

    if step == "collecting_datetime":
        if not is_valid_datetime_text(message):
            return ChatResult("Please provide a preferred date or time (e.g., 'Tomorrow at 2 PM' or 'Monday morning').")
        lead = lead_service.create_lead(
            db, name=state.get("name"), phone=state.get("phone"), service=state.get("requested_service"),
            preferred_datetime=message, conversation_id=conversation.id,
        )
        conversation.customer_id = lead.customer_id or conversation.customer_id
        _reset(conversation)
        return ChatResult(f"You're all set, {lead.name}! I've saved your request and our team will contact you.",
                          events=["lead_created"])

    # --- Human handoff flow ------------------------------------------------
    if step == "handoff_collecting_name":
        if not is_valid_name(message):
            return ChatResult("Could you tell me your name, so our team knows who to contact?")
        state["name"] = clean_text(message, 100)
        save_state(conversation, state)
        conversation.current_step = "handoff_collecting_phone"
        return ChatResult(f"Thanks, {state['name']}. What phone number can our team reach you on?")

    if step == "handoff_collecting_phone":
        if not is_valid_phone(message):
            return ChatResult("That doesn't look like a valid phone number. Please enter a valid phone number.")
        lead_service.request_handoff(db, conversation, reason=None, name=state.get("name"), phone=message)
        _reset(conversation)
        conversation.status = "handoff"
        return ChatResult("Thank you. I've added your contact details to the request. A member of our team will "
                          "contact you as soon as possible.", events=["handoff_updated"])

    # --- No active flow: work out what the customer wants -----------------
    # Short yes/no answers depend on what Ava just asked, so they never go to the classifier.
    is_manage = any(k in lower for k in MANAGE_CANCEL + MANAGE_RESCHEDULE)
    if lower in YES_WORDS:
        return _affirm(db, conversation)
    if _is_negative(lower) and not is_manage:
        return _decline(conversation)

    intent = predict_intent(message)
    _, confidence = classify(message)
    conversation.intent = intent
    if intent == "affirm" and confidence >= HANDOFF_MIN_CONFIDENCE:
        return _affirm(db, conversation)
    if intent == "decline" and confidence >= HANDOFF_MIN_CONFIDENCE and not is_manage:
        return _decline(conversation)

    wants_cancel = intent == "cancel_appointment" or any(k in lower for k in MANAGE_CANCEL)
    wants_reschedule = intent == "reschedule_appointment" or any(k in lower for k in MANAGE_RESCHEDULE)
    if wants_cancel or wants_reschedule:
        mode = "cancel" if wants_cancel else "reschedule"
        save_state(conversation, {"mode": mode})
        conversation.current_step = "manage_collecting_code"
        verb = "cancel" if mode == "cancel" else "reschedule"
        return ChatResult(f"I can help you {verb} your appointment. What is your booking code? (e.g. AVA-7K3P9Q)")

    confident_handoff = (intent in {"complaint", "follow_up"} and confidence >= HANDOFF_MIN_CONFIDENCE
                         and len(lower.split()) >= HANDOFF_MIN_WORDS)
    if any(k in lower for k in HANDOFF_KEYWORDS) or intent == "human_escalation" or confident_handoff:
        reason = {"complaint": "Complaint: ", "follow_up": "Follow-up on an earlier request: "}.get(
            intent if confident_handoff else "", "")
        lead_service.request_handoff(db, conversation, reason=reason + (clean_text(message, 1900) or ""))
        if confident_handoff and intent == "complaint":
            opening = "I'm sorry to hear that. I've asked a member of our team to look into it."
        elif confident_handoff and intent == "follow_up":
            opening = "Thanks for following up. I've asked our team to check on your earlier request."
        else:
            opening = "I've requested help from a member of our team."
        conversation.current_step = "handoff_collecting_name"
        return ChatResult(
            f"{opening} Nobody has replied yet; they will contact you as soon as possible. "
            "To make sure they can reach you, what is your name?",
            events=["handoff_requested"],
        )

    if intent == "appointment" or any(k in lower for k in BOOK_KEYWORDS):
        save_state(conversation, {"mode": "book"})
        conversation.current_step = "booking_collecting_name"
        return ChatResult("I would love to help you schedule an appointment! To get started, what is your full name?")

    if intent == "lead_inquiry" or any(k in lower for k in LEAD_KEYWORDS):
        save_state(conversation, {})
        conversation.current_step = "collecting_name"
        return ChatResult("I'll take your details so our team can get back to you. What is your full name?")

    faq_answer = faq_service.best_answer(db, message)
    if faq_answer:
        return ChatResult(faq_answer)

    name = business_service.business_name(db)
    if intent == "business_hours":
        return ChatResult(f"Our opening hours are:\n{business_service.format_business_hours(db)}")
    if intent in {"services", "pricing"}:
        services = business_service.get_services(db)
        if services:
            lines = [f"- {s['name']}" + (f": {s['price']}" if intent == "pricing" and s["price"] else "")
                     for s in services]
            return ChatResult("Here is what we offer:\n" + "\n".join(lines)
                              + "\n\nWould you like to book an appointment?")
    if intent == "contact":
        info = business_service.get_business_information(db)
        parts = [f"Phone: {info['phone']}" if info["phone"] else None,
                 f"E-mail: {info['email']}" if info["email"] else None,
                 f"Address: {info['address']}" if info["address"] else None]
        parts = [p for p in parts if p]
        if parts:
            return ChatResult("You can reach us here:\n" + "\n".join(parts))
    if intent == "greeting":
        return ChatResult(f"Hello! Welcome to {name}. How can I help you today? Would you like to explore our "
                          "services or book an appointment?")
    if intent == "goodbye":
        return ChatResult("Goodbye! Feel free to reach out if you have any more questions. Have a great day!")
    if intent == "thanks":
        return ChatResult("You're welcome! Is there anything else I can help you with?")
    if intent == "out_of_scope":
        return ChatResult(f"I'm the receptionist for {name}, so I can only help with our services, prices, opening "
                          "hours and appointments. What can I do for you?")

    return ChatResult("I'm not sure I have the answer to that. I can tell you about our services, prices and opening "
                      "hours, book or change an appointment, or ask a member of our team to contact you.")
