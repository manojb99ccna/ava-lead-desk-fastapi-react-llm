"""Read access to verified business information (settings, hours, services)."""
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from ..models import AvaBusinessSetting, AvaBusinessWorkingHour, AvaService

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DEFAULT_TIMEZONE = "Asia/Kolkata"


class _DefaultSettings:
    """Used only when the settings row has not been created yet."""

    id = None
    business_name = None
    description = None
    phone = None
    email = None
    address = None
    website = None
    timezone = DEFAULT_TIMEZONE
    appointment_duration_minutes = 60
    booking_window_days = 7


def get_settings(db: Session):
    return db.query(AvaBusinessSetting).order_by(AvaBusinessSetting.id.asc()).first() or _DefaultSettings()


def get_timezone(settings_row) -> ZoneInfo:
    try:
        return ZoneInfo(settings_row.timezone or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TIMEZONE)


def local_now(settings_row) -> datetime:
    """Current business-local time as a naive datetime (appointments are stored naive, local)."""
    return datetime.now(get_timezone(settings_row)).replace(tzinfo=None, microsecond=0)


def business_name(db: Session) -> str:
    return get_settings(db).business_name or "our business"


def get_business_information(db: Session) -> dict:
    s = get_settings(db)
    return {
        "business_name": s.business_name,
        "description": s.description,
        "phone": s.phone,
        "email": s.email,
        "address": s.address,
        "website": s.website,
        "timezone": s.timezone,
        "appointment_duration_minutes": s.appointment_duration_minutes,
        "booking_window_days": s.booking_window_days,
    }


def get_business_hours(db: Session) -> list[dict]:
    rows = {r.day_of_week: r for r in db.query(AvaBusinessWorkingHour).all()}
    result = []
    for day in range(7):
        row = rows.get(day)
        is_open = bool(row and row.is_open and row.opening_time and row.closing_time)
        result.append({
            "day_of_week": day,
            "day": DAY_NAMES[day],
            "is_open": is_open,
            "opening_time": row.opening_time.strftime("%H:%M") if is_open else None,
            "closing_time": row.closing_time.strftime("%H:%M") if is_open else None,
        })
    return result


def format_business_hours(db: Session) -> str:
    lines = []
    for item in get_business_hours(db):
        if item["is_open"]:
            lines.append(f"{item['day']}: {item['opening_time']} - {item['closing_time']}")
        else:
            lines.append(f"{item['day']}: Closed")
    return "\n".join(lines)


def get_services(db: Session, active_only: bool = True) -> list[dict]:
    query = db.query(AvaService)
    if active_only:
        query = query.filter(AvaService.is_active.is_(True))
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "price": s.price,
            "duration_minutes": s.duration_minutes,
        }
        for s in query.order_by(AvaService.name.asc()).all()
    ]
