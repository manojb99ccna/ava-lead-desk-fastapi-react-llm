from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..auth import require_staff
from ..database import get_db
from ..models import Admin, AvaAppointment, AvaConversation, AvaCustomer, AvaLead
from .appointments import appointment_out

router = APIRouter(prefix="/api/admin/customers", tags=["admin-customers"])


def customer_out(c: AvaCustomer) -> dict:
    return {"id": c.id, "name": c.name, "phone": c.phone, "email": c.email,
            "created_at": c.created_at, "updated_at": c.updated_at}


@router.get("")
def list_customers(q: str | None = Query(default=None, max_length=100), _: Admin = Depends(require_staff),
                   db: Session = Depends(get_db)):
    appt_counts = (
        db.query(AvaAppointment.customer_id, func.count(AvaAppointment.id).label("n"))
        .group_by(AvaAppointment.customer_id).subquery()
    )
    lead_counts = (
        db.query(AvaLead.customer_id, func.count(AvaLead.id).label("n")).group_by(AvaLead.customer_id).subquery()
    )
    query = (
        db.query(AvaCustomer, appt_counts.c.n, lead_counts.c.n)
        .outerjoin(appt_counts, appt_counts.c.customer_id == AvaCustomer.id)
        .outerjoin(lead_counts, lead_counts.c.customer_id == AvaCustomer.id)
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(AvaCustomer.name.ilike(like), AvaCustomer.phone.ilike(like),
                                 AvaCustomer.email.ilike(like)))
    rows = query.order_by(AvaCustomer.updated_at.desc(), AvaCustomer.id.desc()).limit(500).all()
    return [{**customer_out(c), "appointments": a or 0, "leads": l or 0} for c, a, l in rows]


@router.get("/{customer_id}")
def get_customer(customer_id: int, _: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    customer = db.get(AvaCustomer, customer_id)
    if not customer:
        raise HTTPException(404, "Customer not found")
    appointments = (db.query(AvaAppointment).filter(AvaAppointment.customer_id == customer.id)
                    .order_by(AvaAppointment.appointment_date.desc()).all())
    leads = db.query(AvaLead).filter(AvaLead.customer_id == customer.id).order_by(AvaLead.id.desc()).all()
    conversations = (db.query(AvaConversation).filter(AvaConversation.customer_id == customer.id)
                     .order_by(AvaConversation.updated_at.desc()).all())
    return {
        "customer": customer_out(customer),
        "appointments": [appointment_out(a) for a in appointments],
        "leads": [{"id": l.id, "requested_service": l.requested_service, "status": l.status,
                   "created_at": l.created_at} for l in leads],
        "conversations": [{"id": c.id, "status": c.status, "updated_at": c.updated_at} for c in conversations],
    }
