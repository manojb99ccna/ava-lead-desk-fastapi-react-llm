"""Appointment rules: availability, booking, rescheduling, cancelling and history.

All dates and times are business-local and stored as naive datetimes.
Double booking is prevented by locking the working-hours row of the target weekday
(SELECT ... FOR UPDATE) before checking for overlaps, so two concurrent bookings for the
same day are checked one after the other.
"""
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    APPOINTMENT_STATUSES,
    BLOCKING_STATUSES,
    AvaAppointment,
    AvaAppointmentHistory,
    AvaBusinessWorkingHour,
)
from . import business_service
from .customer_service import find_or_create_customer
from .validation import (
    clean_text,
    is_valid_email,
    is_valid_name,
    is_valid_phone,
    normalize_booking_code,
    normalize_phone,
)

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I to avoid confusion


class AppointmentError(Exception):
    """A rule violation with a customer-safe message."""

    def __init__(self, code: str, message: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


@dataclass
class _Context:
    duration: int
    window_days: int
    now: datetime


def _context(db: Session, now: datetime | None = None) -> _Context:
    s = business_service.get_settings(db)
    return _Context(
        duration=max(5, int(s.appointment_duration_minutes or 60)),
        window_days=max(1, int(s.booking_window_days or 7)),
        now=now or business_service.local_now(s),
    )


def _working_hour(db: Session, day: date, lock: bool = False):
    query = db.query(AvaBusinessWorkingHour).filter(AvaBusinessWorkingHour.day_of_week == day.weekday())
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row and row.is_open and row.opening_time and row.closing_time and row.opening_time < row.closing_time:
        return row
    return None


def _blocking_appointments(db: Session, day: date, exclude_id: int | None = None):
    start = datetime.combine(day, time.min)
    query = db.query(AvaAppointment).filter(
        AvaAppointment.appointment_date >= start - timedelta(days=1),  # catches long ones from the day before
        AvaAppointment.appointment_date < start + timedelta(days=1),
        AvaAppointment.status.in_(BLOCKING_STATUSES),
    )
    if exclude_id is not None:
        query = query.filter(AvaAppointment.id != exclude_id)
    return query.all()


def _overlaps(start: datetime, end: datetime, appointments) -> bool:
    return any(
        a.appointment_date < end and a.appointment_date + timedelta(minutes=a.duration_minutes) > start
        for a in appointments
    )


def _in_window(ctx: _Context, day: date) -> bool:
    today = ctx.now.date()
    return today <= day <= today + timedelta(days=ctx.window_days - 1)


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------


def available_slots(
    db: Session, day: date, now: datetime | None = None, exclude_appointment_id: int | None = None
) -> list[dict]:
    ctx = _context(db, now)
    if not _in_window(ctx, day):
        return []
    hours = _working_hour(db, day)
    if not hours:
        return []

    booked = _blocking_appointments(db, day, exclude_appointment_id)
    slots = []
    slot_start = datetime.combine(day, hours.opening_time)
    closing = datetime.combine(day, hours.closing_time)
    while slot_start + timedelta(minutes=ctx.duration) <= closing:
        slot_end = slot_start + timedelta(minutes=ctx.duration)
        available = slot_start > ctx.now and not _overlaps(slot_start, slot_end, booked)
        slots.append({
            "time": slot_start.strftime("%H:%M"),
            "label": slot_start.strftime("%I:%M %p"),
            "available": available,
            "disabled": not available,
        })
        slot_start = slot_end
    return slots


def available_dates(db: Session, now: datetime | None = None, exclude_appointment_id: int | None = None) -> list[dict]:
    ctx = _context(db, now)
    result = []
    for offset in range(ctx.window_days):
        day = ctx.now.date() + timedelta(days=offset)
        is_open = _working_hour(db, day) is not None
        free = (
            sum(1 for s in available_slots(db, day, ctx.now, exclude_appointment_id) if s["available"])
            if is_open
            else 0
        )
        result.append({
            "date": day.isoformat(),
            "label": day.strftime("%d %b %Y"),
            "day": day.strftime("%A"),
            "is_open": is_open,
            "available_slots": free,
            "disabled": free == 0,
        })
    return result


def validate_slot(
    db: Session,
    day: date,
    start: time,
    now: datetime | None = None,
    exclude_appointment_id: int | None = None,
    lock: bool = False,
) -> tuple[datetime, int]:
    """Raises AppointmentError when the slot cannot be booked. Returns (start datetime, duration)."""
    ctx = _context(db, now)
    if not _in_window(ctx, day):
        raise AppointmentError(
            "outside_window",
            f"Appointments can only be booked from today up to {ctx.window_days} days ahead.",
        )
    hours = _working_hour(db, day, lock=lock)
    if not hours:
        raise AppointmentError("closed", f"We are closed on {day.strftime('%A, %d %b %Y')}.")

    start_dt = datetime.combine(day, start.replace(second=0, microsecond=0))
    end_dt = start_dt + timedelta(minutes=ctx.duration)
    opening = datetime.combine(day, hours.opening_time)
    closing = datetime.combine(day, hours.closing_time)

    if start_dt < opening or end_dt > closing:
        raise AppointmentError(
            "outside_hours",
            f"That time is outside our opening hours ({hours.opening_time.strftime('%H:%M')}"
            f" - {hours.closing_time.strftime('%H:%M')}).",
        )
    if (start_dt - opening).total_seconds() % (ctx.duration * 60) != 0:
        raise AppointmentError("invalid_slot", "Please choose one of the listed appointment times.")
    if start_dt <= ctx.now:
        raise AppointmentError("past", "That time has already passed. Please choose a later time.")
    if _overlaps(start_dt, end_dt, _blocking_appointments(db, day, exclude_appointment_id)):
        raise AppointmentError("slot_taken", "Sorry, that time slot is already booked.", http_status=409)
    return start_dt, ctx.duration


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------


def _new_booking_code(db: Session) -> str:
    for _ in range(20):
        code = "AVA-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if not db.query(AvaAppointment.id).filter(AvaAppointment.booking_code == code).first():
            return code
    raise AppointmentError("code_failure", "Could not create a booking reference. Please try again.", 500)


def _history(db, appointment, action, actor, old_date=None, old_status=None, note=None):
    db.add(AvaAppointmentHistory(
        appointment_id=appointment.id,
        action=action,
        old_appointment_date=old_date,
        new_appointment_date=appointment.appointment_date,
        old_status=old_status,
        new_status=appointment.status,
        actor=actor,
        note=note,
    ))


def _commit(db: Session, commit: bool):
    if not commit:
        db.flush()
        return
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppointmentError("conflict", "The appointment could not be saved. Please try again.", 409) from exc


def book_appointment(
    db: Session,
    *,
    name: str,
    phone: str,
    service: str,
    day: date,
    start: time,
    email: str | None = None,
    notes: str | None = None,
    source: str = "website_chat",
    actor: str = "customer",
    conversation_id: int | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> AvaAppointment:
    if not is_valid_name(name):
        raise AppointmentError("invalid_name", "Please provide a valid full name.")
    if not is_valid_phone(phone):
        raise AppointmentError("invalid_phone", "Please provide a valid phone number (10-15 digits).")
    if email and not is_valid_email(email):
        raise AppointmentError("invalid_email", "Please provide a valid e-mail address.")
    service = clean_text(service, 255)
    if not service or len(service) < 2:
        raise AppointmentError("invalid_service", "Please tell us which service the appointment is for.")

    start_dt, duration = validate_slot(db, day, start, now=now, lock=True)

    customer = find_or_create_customer(db, name, phone, email)
    appointment = AvaAppointment(
        booking_code=_new_booking_code(db),
        name=clean_text(name, 100),
        phone=normalize_phone(phone),
        email=email.strip() if email else None,
        service=service,
        appointment_date=start_dt,
        duration_minutes=duration,
        status="pending",
        notes=clean_text(notes, 2000),
        source=source,
        customer_id=customer.id if customer else None,
        conversation_id=conversation_id,
    )
    db.add(appointment)
    db.flush()
    _history(db, appointment, "created", actor)
    _commit(db, commit)
    return appointment


def find_customer_appointment(db: Session, booking_code: str, phone: str) -> AvaAppointment:
    """Ownership check for customers: the booking code AND the phone number must match."""
    code = normalize_booking_code(booking_code)
    appointment = db.query(AvaAppointment).filter(AvaAppointment.booking_code == code).first() if code else None
    if not appointment or normalize_phone(appointment.phone) != normalize_phone(phone):
        # Same message for both cases so codes cannot be probed.
        raise AppointmentError(
            "not_found", "I could not find an appointment with that booking code and phone number.", 404
        )
    return appointment


def _ensure_changeable(appointment: AvaAppointment, now: datetime):
    if appointment.status not in BLOCKING_STATUSES:
        raise AppointmentError("not_active", f"This appointment is already {appointment.status}.", 409)
    if appointment.appointment_date <= now:
        raise AppointmentError("in_past", "This appointment has already taken place and cannot be changed.", 409)


def reschedule_appointment(
    db: Session,
    appointment: AvaAppointment,
    day: date,
    start: time,
    actor: str,
    now: datetime | None = None,
    commit: bool = True,
) -> AvaAppointment:
    ctx = _context(db, now)
    _ensure_changeable(appointment, ctx.now)
    start_dt, duration = validate_slot(db, day, start, now=ctx.now, exclude_appointment_id=appointment.id, lock=True)
    if start_dt == appointment.appointment_date:
        raise AppointmentError("same_time", "The appointment is already at that time.")

    old_date = appointment.appointment_date
    appointment.appointment_date = start_dt
    appointment.duration_minutes = duration
    _history(db, appointment, "rescheduled", actor, old_date=old_date, old_status=appointment.status)
    _commit(db, commit)
    return appointment


def cancel_appointment(
    db: Session,
    appointment: AvaAppointment,
    actor: str,
    reason: str | None = None,
    now: datetime | None = None,
    commit: bool = True,
) -> AvaAppointment:
    ctx = _context(db, now)
    _ensure_changeable(appointment, ctx.now)
    old_status = appointment.status
    appointment.status = "cancelled"
    appointment.cancelled_at = ctx.now
    _history(db, appointment, "cancelled", actor, old_date=appointment.appointment_date,
             old_status=old_status, note=clean_text(reason, 500))
    _commit(db, commit)
    return appointment


def change_status(db: Session, appointment: AvaAppointment, status: str, actor: str, commit: bool = True):
    if status not in APPOINTMENT_STATUSES:
        raise AppointmentError("invalid_status", f"Status must be one of: {', '.join(APPOINTMENT_STATUSES)}.")
    if status == appointment.status:
        return appointment
    if status in BLOCKING_STATUSES and appointment.status not in BLOCKING_STATUSES:
        # Re-activating a cancelled appointment must not create a double booking.
        start = appointment.appointment_date
        end = start + timedelta(minutes=appointment.duration_minutes)
        if _overlaps(start, end, _blocking_appointments(db, start.date(), appointment.id)):
            raise AppointmentError("slot_taken", "Another appointment now occupies this time slot.", 409)
    old_status = appointment.status
    appointment.status = status
    if status == "cancelled":
        appointment.cancelled_at = business_service.local_now(business_service.get_settings(db))
    _history(db, appointment, "status_changed", actor, old_date=appointment.appointment_date, old_status=old_status)
    _commit(db, commit)
    return appointment


def to_public_dict(appointment: AvaAppointment) -> dict:
    """Safe summary for customers (no internal ids or notes)."""
    return {
        "booking_code": appointment.booking_code,
        "name": appointment.name,
        "service": appointment.service,
        "date": appointment.appointment_date.date().isoformat(),
        "time": appointment.appointment_date.strftime("%H:%M"),
        "display": appointment.appointment_date.strftime("%A, %d %b %Y at %I:%M %p"),
        "duration_minutes": appointment.duration_minutes,
        "status": appointment.status,
    }
