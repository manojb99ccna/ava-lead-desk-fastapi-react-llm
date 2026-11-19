from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..auth import require_admin, require_staff
from ..database import get_db
from ..models import LEAD_STATUSES, Admin, AvaLead

router = APIRouter(prefix="/api/admin/leads", tags=["admin-leads"])


class LeadResponse(BaseModel):
    id: int
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    requested_service: str | None = None
    preferred_datetime: str | None = None
    message: str | None = None
    notes: str | None = None
    status: str
    source: str
    customer_id: int | None = None
    conversation_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class LeadUpdate(BaseModel):
    status: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


@router.get("", response_model=list[LeadResponse])
def get_admin_leads(
    status: str | None = None,
    q: str | None = Query(default=None, max_length=100),
    _: Admin = Depends(require_staff),
    db: Session = Depends(get_db),
):
    query = db.query(AvaLead)
    if status:
        query = query.filter(AvaLead.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(AvaLead.name.ilike(like), AvaLead.phone.ilike(like), AvaLead.email.ilike(like),
                                 AvaLead.requested_service.ilike(like)))
    return query.order_by(AvaLead.created_at.desc(), AvaLead.id.desc()).limit(500).all()


@router.patch("/{lead_id}", response_model=LeadResponse)
def update_lead(lead_id: int, data: LeadUpdate, _: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    lead = db.get(AvaLead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    if data.status is not None:
        if data.status not in LEAD_STATUSES:
            raise HTTPException(422, f"Status must be one of: {', '.join(LEAD_STATUSES)}")
        lead.status = data.status
    if data.notes is not None:
        lead.notes = data.notes.strip() or None
    db.commit()
    return lead


@router.delete("/{lead_id}")
def delete_lead(lead_id: int, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    lead = db.get(AvaLead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    db.delete(lead)
    db.commit()
    return {"success": True}
