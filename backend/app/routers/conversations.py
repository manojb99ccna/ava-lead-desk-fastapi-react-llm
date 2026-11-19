from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_staff
from ..database import get_db
from ..models import Admin, AvaConversation, AvaMessage

router = APIRouter(prefix="/api/admin/conversations", tags=["admin-conversations"])


class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender: str
    message: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


@router.get("")
def get_conversations(
    status: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    _: Admin = Depends(require_staff),
    db: Session = Depends(get_db),
):
    counts = (db.query(AvaMessage.conversation_id, func.count(AvaMessage.id).label("n"))
              .group_by(AvaMessage.conversation_id).subquery())
    query = db.query(AvaConversation, counts.c.n).outerjoin(counts, counts.c.conversation_id == AvaConversation.id)
    if status:
        query = query.filter(AvaConversation.status == status)
    rows = query.order_by(AvaConversation.updated_at.desc(), AvaConversation.id.desc()).limit(limit).all()
    return [
        {
            "id": c.id, "session_id": c.session_id, "intent": c.intent, "current_step": c.current_step,
            "status": c.status, "engine": c.engine, "channel": c.channel, "customer_id": c.customer_id, "message_count": n or 0,
            "created_at": c.created_at, "updated_at": c.updated_at,
        }
        for c, n in rows
    ]


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def get_conversation_messages(conversation_id: int, _: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    if not db.get(AvaConversation, conversation_id):
        raise HTTPException(404, "Conversation not found")
    return (db.query(AvaMessage).filter(AvaMessage.conversation_id == conversation_id)
            .order_by(AvaMessage.id.asc()).all())
