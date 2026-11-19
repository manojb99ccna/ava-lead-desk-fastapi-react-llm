"""Admin appointment management (login required)."""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import require_staff
from ..database import get_db
from ..models import APPOINTMENT_STATUSES, Admin, AvaAppointment, AvaAppointmentHistory
from ..services import appointment_service as appts
from ..services.appointment_service import AppointmentError

router = APIRouter(prefix="/api/admin/appointments", tags=["admin-appointments"])


def appointment_out(a: AvaAppointment) -> dict:
    return {
        "id": a.id, "booking_code": a.booking_code, "name": a.name, "phone": a.phone, "email": a.email,
        "service": a.service, "appointment_date": a.appointment_date, "duration_minutes": a.duration_minutes,
        "status": a.status, "notes": a.notes, "source": a.source, "customer_id": a.customer_id,
        "conversation_id": a.conversation_id, "cancelled_at": a.cancelled_at, "created_at": a.created_at,
        "updated_at": a.updated_at,
    }


def _actor(admin: Admin) -> str:
    return f"admin:{admin.username}"


def _get(db: Session, appointment_id: int) -> AvaAppointment:
    appointment = db.get(AvaAppointment, appointment_id)
    if not appointment:
        raise HTTPException(404, "Appointment not found")
    return appointment


def _fail(db: Session, exc: AppointmentError):
    db.rollback()
    raise HTTPException(exc.http_status, exc.message)


class AdminBooking(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)
    service: str = Field(min_length=2, max_length=255)
    appointment_date: date
    start_time: time
    notes: str | None = Field(default=None, max_length=2000)


class AppointmentUpdate(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class RescheduleIn(BaseModel):
    new_date: date
    new_time: time


class CancelIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


@router.get("")
def list_appointments(
    status: str | None = Query(default=None),
    date_from: date | None = None,
    date_to: date | None = None,
    q: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=200, ge=1, le=1000),
    _: Admin = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = db.query(AvaAppointment)
    if status:
        if status not in APPOINTMENT_STATUSES:
            raise HTTPException(422, "Invalid status")
        query = query.filter(AvaAppointment.status == status)
    if date_from:
        query = query.filter(AvaAppointment.appointment_date >= datetime.combine(date_from, time.min))
    if date_to:
        query = query.filter(AvaAppointment.appointment_date < datetime.combine(date_to + timedelta(days=1), time.min))
    if q:
        like = f"%{q.strip()}%"  # bound parameter: safe from SQL injection
        query = query.filter(or_(AvaAppointment.name.ilike(like), AvaAppointment.phone.ilike(like),
                                 AvaAppointment.booking_code.ilike(like), AvaAppointment.service.ilike(like)))
    rows = query.order_by(AvaAppointment.appointment_date.asc()).limit(limit).all()
    return [appointment_out(a) for a in rows]


@router.get("/availability")
def availability(selected_date: date | None = None, _: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    if selected_date:
        return {"date": selected_date.isoformat(), "slots": appts.available_slots(db, selected_date)}
    return {"dates": appts.available_dates(db)}


@router.get("/{appointment_id}")
def get_appointment(appointment_id: int, _: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    appointment = _get(db, appointment_id)
    history = (
        db.query(AvaAppointmentHistory)
        .filter(AvaAppointmentHistory.appointment_id == appointment.id)
        .order_by(AvaAppointmentHistory.id.asc())
        .all()
    )
    return {
        "appointment": appointment_out(appointment),
        "history": [
            {"id": h.id, "action": h.action, "old_appointment_date": h.old_appointment_date,
             "new_appointment_date": h.new_appointment_date, "old_status": h.old_status, "new_status": h.new_status,
             "actor": h.actor, "note": h.note, "created_at": h.created_at}
            for h in history
        ],
    }


@router.post("", status_code=201)
def create_appointment(data: AdminBooking, admin: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    try:
        appointment = appts.book_appointment(
            db, name=data.name, phone=data.phone, email=data.email, service=data.service,
            day=data.appointment_date, start=data.start_time, notes=data.notes, source="admin", actor=_actor(admin),
        )
    except AppointmentError as exc:
        _fail(db, exc)
    return appointment_out(appointment)


@router.patch("/{appointment_id}")
def update_appointment(appointment_id: int, data: AppointmentUpdate, admin: Admin = Depends(require_staff),
                       db: Session = Depends(get_db)):
    appointment = _get(db, appointment_id)
    try:
        if data.notes is not None:
            appointment.notes = data.notes.strip() or None
        if data.status:
            appts.change_status(db, appointment, data.status, _actor(admin), commit=False)
        db.commit()
    except AppointmentError as exc:
        _fail(db, exc)
    return appointment_out(appointment)


@router.post("/{appointment_id}/reschedule")
def reschedule(appointment_id: int, data: RescheduleIn, admin: Admin = Depends(require_staff),
               db: Session = Depends(get_db)):
    appointment = _get(db, appointment_id)
    try:
        appts.reschedule_appointment(db, appointment, data.new_date, data.new_time, actor=_actor(admin))
    except AppointmentError as exc:
        _fail(db, exc)
    return appointment_out(appointment)


@router.post("/{appointment_id}/cancel")
def cancel(appointment_id: int, data: CancelIn, admin: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    appointment = _get(db, appointment_id)
    try:
        appts.cancel_appointment(db, appointment, actor=_actor(admin), reason=data.reason)
    except AppointmentError as exc:
        _fail(db, exc)
    return appointment_out(appointment)
