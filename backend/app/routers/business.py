"""Business information, opening hours and services (read: staff, write: admin)."""
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from ..auth import require_admin, require_staff
from ..database import get_db
from ..models import Admin, AvaBusinessSetting, AvaBusinessWorkingHour, AvaService
from ..services import business_service
from ..services.validation import is_valid_email

router = APIRouter(prefix="/api/admin/business", tags=["admin-business"])


class SettingsIn(BaseModel):
    business_name: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="Asia/Kolkata", max_length=100)
    appointment_duration_minutes: int = Field(default=60, ge=5, le=480)
    booking_window_days: int = Field(default=7, ge=1, le=365)

    @model_validator(mode="after")
    def _check(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone (use a name like Asia/Kolkata or Europe/London)")
        if self.email and not is_valid_email(self.email):
            raise ValueError("Invalid e-mail address")
        return self


class DayHours(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    is_open: bool
    opening_time: time | None = None
    closing_time: time | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.is_open and (not self.opening_time or not self.closing_time or self.opening_time >= self.closing_time):
            raise ValueError("Open days need an opening time before the closing time")
        return self


class ServiceIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=5000)
    price: str | None = Field(default=None, max_length=100)
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    is_active: bool = True


def service_out(s: AvaService) -> dict:
    return {"id": s.id, "name": s.name, "description": s.description, "price": s.price,
            "duration_minutes": s.duration_minutes, "is_active": s.is_active}


@router.get("/settings")
def get_settings(_: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    return business_service.get_business_information(db)


@router.put("/settings")
def update_settings(data: SettingsIn, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    row = db.query(AvaBusinessSetting).order_by(AvaBusinessSetting.id.asc()).first()
    if row is None:
        row = AvaBusinessSetting()
        db.add(row)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return business_service.get_business_information(db)


@router.get("/hours")
def get_hours(_: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    return business_service.get_business_hours(db)


@router.put("/hours")
def update_hours(days: list[DayHours], _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    if len({d.day_of_week for d in days}) != len(days):
        raise HTTPException(422, "Each weekday may appear only once")
    existing = {r.day_of_week: r for r in db.query(AvaBusinessWorkingHour).all()}
    for d in days:
        row = existing.get(d.day_of_week) or AvaBusinessWorkingHour(day_of_week=d.day_of_week)
        row.is_open = d.is_open
        row.opening_time = d.opening_time if d.is_open else None
        row.closing_time = d.closing_time if d.is_open else None
        db.add(row)
    db.commit()
    return business_service.get_business_hours(db)


@router.get("/services")
def list_services(_: Admin = Depends(require_staff), db: Session = Depends(get_db)):
    return [service_out(s) for s in db.query(AvaService).order_by(AvaService.name.asc()).all()]


@router.post("/services", status_code=201)
def create_service(data: ServiceIn, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    if db.query(AvaService).filter(AvaService.name == data.name).first():
        raise HTTPException(409, "A service with this name already exists")
    service = AvaService(**data.model_dump())
    db.add(service)
    db.commit()
    return service_out(service)


@router.put("/services/{service_id}")
def update_service(service_id: int, data: ServiceIn, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    service = db.get(AvaService, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    clash = db.query(AvaService).filter(AvaService.name == data.name, AvaService.id != service_id).first()
    if clash:
        raise HTTPException(409, "A service with this name already exists")
    for key, value in data.model_dump().items():
        setattr(service, key, value)
    db.commit()
    return service_out(service)


@router.delete("/services/{service_id}")
def delete_service(service_id: int, _: Admin = Depends(require_admin), db: Session = Depends(get_db)):
    service = db.get(AvaService, service_id)
    if not service:
        raise HTTPException(404, "Service not found")
    db.delete(service)
    db.commit()
    return {"success": True}
