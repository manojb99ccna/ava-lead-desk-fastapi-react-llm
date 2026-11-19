from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Record timestamps (created_at, updated_at, ...) stored as naive UTC, returned as aware UTC.

    MySQL's NOW() runs in UTC inside Docker. Returning timezone-aware values makes the API send
    "2026-11-10T04:09:27+00:00", so browsers show the correct local time.

    Appointment times are NOT stored with this type: they are business-local wall-clock times.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
