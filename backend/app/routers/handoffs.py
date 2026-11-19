from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_staff
from ..database import get_db
from ..models import HANDOFF_STATUSES, Admin, AvaConversation, AvaHandoffRequest

router = APIRouter(prefix="/api/admin/handoffs", tags=["admin-handoffs"])


class HandoffUpdate(BaseModel):
    status: str | None = None
    resolution_note: str | None = Field(default=None, max_length=2000)
    assign_to_me: bool = False


def handoff_out(h: AvaHandoffRequest) -> dict:
    return {
        "id": h.id, "conversation_id": h.conversation_id, "customer_id": h.customer_id, "name": h.name,
        "phone": h.phone, "email": h.email, "reason": h.reason, "status": h.status, "assigned_to": h.assigned_to,
        "resolution_note": h.resolution_note, "created_at": h.created_at, "updated_at": h.updated_at,
    }


@router.get("")
def list_handoffs(status: str | None = None, _: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    query = db.query(AvaHandoffRequest)
    if status:
        query = query.filter(AvaHandoffRequest.status == status)
    return [handoff_out(h) for h in query.order_by(AvaHandoffRequest.id.desc()).limit(500).all()]


@router.patch("/{handoff_id}")
def update_handoff(handoff_id: int, data: HandoffUpdate, admin: Admin = Depends(require_staff),
                   db: Session = Depends(get_db)):
    handoff = db.get(AvaHandoffRequest, handoff_id)
    if not handoff:
        raise HTTPException(404, "Handoff request not found")
    if data.status is not None:
        if data.status not in HANDOFF_STATUSES:
            raise HTTPException(422, f"Status must be one of: {', '.join(HANDOFF_STATUSES)}")
        handoff.status = data.status
        if data.status == "resolved":
            conversation = db.get(AvaConversation, handoff.conversation_id)
            if conversation and conversation.status == "handoff":
                conversation.status = "active"
    if data.resolution_note is not None:
        handoff.resolution_note = data.resolution_note.strip() or None
    if data.assign_to_me:
        handoff.assigned_to = admin.username
    db.commit()
    return handoff_out(handoff)
