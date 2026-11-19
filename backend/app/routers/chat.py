"""Public chat API used by the website widget."""
from datetime import date, time

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.rate_limit import rate_limit
from ..database import get_db
from ..models import AvaMessage
from ..ai.chat_types import ChatTurn
from ..services import business_service, chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])

chat_limit = rate_limit("chat", lambda: settings.rate_limit_chat_per_minute)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    session_id: str | None = Field(default=None, max_length=100)
    action: str | None = Field(default=None, pattern="^(select_date|select_time)$")
    selected_date: date | None = None
    selected_time: time | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    ui_action: str | None = None
    data: dict | None = None
    engine: str


class SessionRequest(BaseModel):
    session_id: str = Field(max_length=100)


@router.post("", response_model=ChatResponse, dependencies=[Depends(chat_limit)])
def chat(request: ChatRequest, db: Session = Depends(get_db)):
    if not request.message.strip() and not request.action:
        raise HTTPException(422, "Please enter a message.")
    if request.action == "select_date" and not request.selected_date:
        raise HTTPException(422, "Please select a valid date.")
    if request.action == "select_time" and not (request.selected_date and request.selected_time):
        raise HTTPException(422, "Please select a valid date and time.")

    turn = ChatTurn(message=request.message, action=request.action,
                    selected_date=request.selected_date, selected_time=request.selected_time)
    result, conversation = chat_service.handle_chat(db, request.session_id, turn)
    return ChatResponse(reply=result.reply, session_id=conversation.session_id, ui_action=result.ui_action,
                        data=result.data, engine=result.engine)


@router.get("/history", dependencies=[Depends(chat_limit)])
def history(session_id: str = Query(max_length=100), db: Session = Depends(get_db)):
    """Messages of the caller's own conversation. The random session id acts as the access key."""
    conversation = chat_service.get_conversation(db, session_id)
    if not conversation:
        raise HTTPException(404, "Conversation not found")
    messages = (
        db.query(AvaMessage)
        .filter(AvaMessage.conversation_id == conversation.id)
        .order_by(AvaMessage.id.asc())
        .limit(200)
        .all()
    )
    return {
        "session_id": conversation.session_id,
        "messages": [{"from": m.sender, "text": m.message, "created_at": m.created_at} for m in messages],
    }


@router.post("/end", dependencies=[Depends(chat_limit)])
def end_conversation(request: SessionRequest, db: Session = Depends(get_db)):
    """Called by the widget's "New chat" button."""
    conversation = chat_service.get_conversation(db, request.session_id)
    if conversation and conversation.status != "handoff":
        conversation.status = "closed"
        conversation.current_step = None
        conversation.lead_data = "{}"
        db.commit()
    return {"success": True}


@router.get("/info")
def public_info(db: Session = Depends(get_db)):
    """Public business details shown by the chat widget (name, hours, services)."""
    info = business_service.get_business_information(db)
    return {
        "business_name": info["business_name"],
        "hours": business_service.get_business_hours(db),
        "services": business_service.get_services(db),
    }
