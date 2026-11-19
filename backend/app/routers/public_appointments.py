"""Public appointment API for customers (no login).

Viewing, rescheduling and cancelling an existing booking require the booking code AND the phone
number used for the booking.
"""
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.rate_limit import rate_limit
from ..database import get_db
from ..services import appointment_service as appts
from ..services.appointment_service import AppointmentError

router = APIRouter(prefix="/api/appointments", tags=["appointments (public)"])

read_limit = rate_limit("appt_read", lambda: settings.rate_limit_chat_per_minute)
write_limit = rate_limit("appt_write", lambda: settings.rate_limit_booking_per_minute)


def _fail(exc: AppointmentError):
    raise HTTPException(exc.http_status, exc.message)


class BookingRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    service: str = Field(min_length=2, max_length=255)
    appointment_date: date
    start_time: time
    notes: str | None = Field(default=None, max_length=1000)


class LookupRequest(BaseModel):
    booking_code: str = Field(min_length=4, max_length=16)
    phone: str = Field(min_length=7, max_length=30)


class RescheduleRequest(LookupRequest):
    new_date: date
    new_time: time


class CancelRequest(LookupRequest):
    reason: str | None = Field(default=None, max_length=500)


@router.get("/available-dates", dependencies=[Depends(read_limit)])
def available_dates(db: Session = Depends(get_db)):
    return {"dates": appts.available_dates(db)}


@router.get("/available-slots", dependencies=[Depends(read_limit)])
def available_slots(selected_date: date = Query(...), db: Session = Depends(get_db)):
    return {"date": selected_date.isoformat(), "slots": appts.available_slots(db, selected_date)}


@router.post("", status_code=201, dependencies=[Depends(write_limit)])
def book(request: BookingRequest, db: Session = Depends(get_db)):
    try:
        appointment = appts.book_appointment(
            db, name=request.name, phone=request.phone, email=request.email, service=request.service,
            day=request.appointment_date, start=request.start_time, notes=request.notes,
            source="website_form", actor="customer",
        )
    except AppointmentError as exc:
        db.rollback()
        _fail(exc)
    return {"success": True, "message": "Appointment request submitted", "appointment": appts.to_public_dict(appointment)}


@router.post("/lookup", dependencies=[Depends(write_limit)])
def lookup(request: LookupRequest, db: Session = Depends(get_db)):
    try:
        appointment = appts.find_customer_appointment(db, request.booking_code, request.phone)
    except AppointmentError as exc:
        _fail(exc)
    return {"appointment": appts.to_public_dict(appointment)}


@router.post("/reschedule", dependencies=[Depends(write_limit)])
def reschedule(request: RescheduleRequest, db: Session = Depends(get_db)):
    try:
        appointment = appts.find_customer_appointment(db, request.booking_code, request.phone)
        appts.reschedule_appointment(db, appointment, request.new_date, request.new_time, actor="customer")
    except AppointmentError as exc:
        db.rollback()
        _fail(exc)
    return {"success": True, "message": "Appointment rescheduled", "appointment": appts.to_public_dict(appointment)}


@router.post("/cancel", dependencies=[Depends(write_limit)])
def cancel(request: CancelRequest, db: Session = Depends(get_db)):
    try:
        appointment = appts.find_customer_appointment(db, request.booking_code, request.phone)
        appts.cancel_appointment(db, appointment, actor="customer", reason=request.reason)
    except AppointmentError as exc:
        db.rollback()
        _fail(exc)
    return {"success": True, "message": "Appointment cancelled", "appointment": appts.to_public_dict(appointment)}
