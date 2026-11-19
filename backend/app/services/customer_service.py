from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import AvaCustomer
from .validation import clean_text, is_valid_email, normalize_phone


def find_or_create_customer(
    db: Session, name: str | None, phone: str | None, email: str | None = None
) -> AvaCustomer | None:
    """Matches returning customers by phone number. Returns None if there is no usable phone."""
    digits = normalize_phone(phone)
    if not 10 <= len(digits) <= 15:
        return None

    customer = db.query(AvaCustomer).filter(AvaCustomer.phone == digits).first()
    if customer is None:
        customer = AvaCustomer(phone=digits)
        try:
            with db.begin_nested():
                db.add(customer)
                db.flush()
        except IntegrityError:
            # Created at the same moment by another request.
            customer = db.query(AvaCustomer).filter(AvaCustomer.phone == digits).first()

    if name:
        customer.name = clean_text(name, 100)
    if email and is_valid_email(email):
        customer.email = email.strip()
    db.flush()
    return customer
