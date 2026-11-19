from sqlalchemy.orm import Session

from ..models import AvaConversation, AvaHandoffRequest, AvaLead
from .customer_service import find_or_create_customer
from .validation import clean_text, is_valid_email, is_valid_phone, normalize_phone


class LeadError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def create_lead(
    db: Session,
    *,
    name: str | None,
    phone: str | None = None,
    email: str | None = None,
    service: str | None = None,
    preferred_datetime: str | None = None,
    message: str | None = None,
    conversation_id: int | None = None,
    source: str = "website_chat",
) -> AvaLead:
    """Validates and stores a lead. A phone number or an e-mail address is required."""
    if phone and not is_valid_phone(phone):
        raise LeadError("The phone number is not valid (10-15 digits).")
    if email and not is_valid_email(email):
        raise LeadError("The e-mail address is not valid.")
    if not phone and not email:
        raise LeadError("A phone number or an e-mail address is needed so the team can reply.")

    customer = find_or_create_customer(db, name, phone, email) if phone else None
    lead = AvaLead(
        name=clean_text(name, 100) or "Website visitor",
        phone=normalize_phone(phone) or None,
        email=email.strip() if email else None,
        requested_service=clean_text(service, 255),
        preferred_datetime=clean_text(preferred_datetime, 100),
        message=clean_text(message, 2000),
        status="new",
        source=source,
        customer_id=customer.id if customer else None,
        conversation_id=conversation_id,
    )
    db.add(lead)
    db.flush()
    return lead


def request_handoff(
    db: Session,
    conversation: AvaConversation,
    *,
    reason: str | None,
    name: str | None = None,
    phone: str | None = None,
    email: str | None = None,
) -> tuple[AvaHandoffRequest, bool]:
    """Creates (or updates) the open handoff request of a conversation. Returns (request, created)."""
    if phone and not is_valid_phone(phone):
        phone = None
    if email and not is_valid_email(email):
        email = None

    customer = find_or_create_customer(db, name, phone, email) if phone else None
    if customer and not conversation.customer_id:
        conversation.customer_id = customer.id

    existing = (
        db.query(AvaHandoffRequest)
        .filter(
            AvaHandoffRequest.conversation_id == conversation.id,
            AvaHandoffRequest.status.in_(("open", "in_progress")),
        )
        .first()
    )
    if existing:
        existing.name = clean_text(name, 100) or existing.name
        existing.phone = normalize_phone(phone) or existing.phone
        existing.email = (email.strip() if email else None) or existing.email
        if reason:
            existing.reason = clean_text(reason, 2000)
        db.flush()
        return existing, False

    handoff = AvaHandoffRequest(
        conversation_id=conversation.id,
        customer_id=customer.id if customer else conversation.customer_id,
        name=clean_text(name, 100),
        phone=normalize_phone(phone) or None,
        email=email.strip() if email else None,
        reason=clean_text(reason, 2000) or "Customer asked to speak with a person.",
        status="open",
    )
    conversation.status = "handoff"
    db.add(handoff)
    db.flush()
    return handoff, True
