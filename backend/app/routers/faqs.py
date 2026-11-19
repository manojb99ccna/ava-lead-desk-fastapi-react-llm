from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_admin, require_staff
from ..database import get_db
from ..models import Admin, AvaBusinessFAQ
from ..services import faq_service

router = APIRouter(prefix="/api/admin/faqs", tags=["admin-faqs"])


class FAQCreateUpdate(BaseModel):
    intent: str = Field(min_length=2, max_length=50, pattern=r"^[A-Za-z0-9_ -]+$")
    question: str = Field(min_length=3, max_length=1000)
    answer: str = Field(min_length=1, max_length=5000)
    is_active: bool = True


class FAQResponse(BaseModel):
    id: int
    intent: str
    question: str
    answer: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


def _get(db: Session, faq_id: int) -> AvaBusinessFAQ:
    faq = db.get(AvaBusinessFAQ, faq_id)
    if not faq:
        raise HTTPException(404, "FAQ not found")
    return faq


@router.get("", response_model=list[FAQResponse])
def get_faqs(_: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    return db.query(AvaBusinessFAQ).order_by(AvaBusinessFAQ.id.desc()).all()


@router.get("/search")
def search_faqs(q: str = Query(min_length=2, max_length=300), _: Admin = Depends(require_staff),
                db: Session = Depends(get_db)):
    """Lets admins test which FAQ Ava would pick for a question."""
    return faq_service.search_faq(db, q, limit=5)


@router.post("", response_model=FAQResponse, status_code=201)
def create_faq(faq_data: FAQCreateUpdate, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    faq = AvaBusinessFAQ(**faq_data.model_dump())
    db.add(faq)
    db.commit()
    return faq


@router.put("/{faq_id}", response_model=FAQResponse)
def update_faq(faq_id: int, faq_data: FAQCreateUpdate, _: Admin = Depends(require_admin),
               db: Session = Depends(get_db)):
    faq = _get(db, faq_id)
    for key, value in faq_data.model_dump().items():
        setattr(faq, key, value)
    db.commit()
    return faq


@router.delete("/{faq_id}")
def delete_faq(faq_id: int, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    db.delete(_get(db, faq_id))
    db.commit()
    return {"success": True, "message": "FAQ deleted successfully"}
