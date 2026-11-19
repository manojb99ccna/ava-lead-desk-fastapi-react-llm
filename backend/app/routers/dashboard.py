from datetime import datetime, time, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..ai.llm_client import llm_status
from ..auth import require_staff
from ..database import get_db
from ..models import Admin, AvaAppointment, AvaConversation, AvaCustomer, AvaHandoffRequest, AvaLead, AvaMessage
from ..routers.appointments import appointment_out
from ..services import business_service

router = APIRouter(prefix="/api/admin/dashboard", tags=["admin-dashboard"])


@router.get("")
def dashboard(_: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    settings_row = business_service.get_settings(db)
    now = business_service.local_now(settings_row)  # business-local, naive (like appointment times)
    today = datetime.combine(now.date(), time.min)
    # Record timestamps (created_at) are UTC: compare them with the business-local midnight in UTC.
    today_utc = datetime.combine(now.date(), time.min, tzinfo=business_service.get_timezone(settings_row))
    week_ago = today_utc - timedelta(days=6)

    def count(model, *filters):
        return db.query(func.count(model.id)).filter(*filters).scalar() or 0

    upcoming = (
        db.query(AvaAppointment)
        .filter(AvaAppointment.appointment_date >= now, AvaAppointment.status.in_(("pending", "confirmed")))
        .order_by(AvaAppointment.appointment_date.asc())
        .limit(5)
        .all()
    )
    by_engine = dict(db.query(AvaConversation.engine, func.count(AvaConversation.id))
                     .group_by(AvaConversation.engine).all())

    return {
        "stats": {
            "appointments_today": count(AvaAppointment, AvaAppointment.appointment_date >= today,
                                        AvaAppointment.appointment_date < today + timedelta(days=1),
                                        AvaAppointment.status.in_(("pending", "confirmed"))),
            "appointments_pending": count(AvaAppointment, AvaAppointment.status == "pending",
                                          AvaAppointment.appointment_date >= now),
            "appointments_upcoming": count(AvaAppointment, AvaAppointment.appointment_date >= now,
                                           AvaAppointment.status.in_(("pending", "confirmed"))),
            "leads_new": count(AvaLead, AvaLead.status == "new"),
            "handoffs_open": count(AvaHandoffRequest, AvaHandoffRequest.status.in_(("open", "in_progress"))),
            "customers_total": count(AvaCustomer),
            "conversations_today": count(AvaConversation, AvaConversation.created_at >= today_utc),
            "conversations_7d": count(AvaConversation, AvaConversation.created_at >= week_ago),
            "messages_7d": count(AvaMessage, AvaMessage.created_at >= week_ago),
        },
        "conversations_by_engine": {str(k or "unknown"): v for k, v in by_engine.items()},
        "upcoming_appointments": [appointment_out(a) for a in upcoming],
        "llm": llm_status(),
    }
