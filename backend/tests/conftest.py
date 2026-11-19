"""Test setup: in-memory SQLite, no migrations, no real LLM, fixed "now"."""
import os
from datetime import date, datetime, timedelta

os.environ.update({
    "DATABASE_URL": "sqlite://",
    "JWT_SECRET": "test-secret-" + "x" * 40,
    "LLM_PROVIDER": "none",
    "RUN_MIGRATIONS_ON_STARTUP": "false",
    "SEED_ON_STARTUP": "false",
    "CHAT_DEBUG_LOGS": "false",
    "ADMIN_USERNAME": "admin",
    "ADMIN_PASSWORD": "admin123",
    "RATE_LIMIT_LOGIN_PER_MINUTE": "1000",
    "RATE_LIMIT_CHAT_PER_MINUTE": "1000",
    "RATE_LIMIT_BOOKING_PER_MINUTE": "1000",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import database  # noqa: E402
from app.ai import llm_client  # noqa: E402
from app.auth import hash_password  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Admin  # noqa: E402
from app.seed import SEED_FILE, seed_business  # noqa: E402
from app.services import business_service  # noqa: E402

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)


@event.listens_for(engine, "connect")
def _fk_on(dbapi_connection, _):
    dbapi_connection.execute("PRAGMA foreign_keys=ON")


TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def next_weekday(weekday: int, after: date | None = None) -> date:
    """Next date (strictly after `after`) with the given weekday (0 = Monday)."""
    d = (after or date.today()) + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


# Fixed clock: a Monday at 08:00, so Tue-Fri of the same week are bookable.
FIXED_NOW = datetime.combine(next_weekday(0), datetime.min.time()).replace(hour=8)


@pytest.fixture(autouse=True)
def _fixed_clock(monkeypatch):
    monkeypatch.setattr(business_service, "local_now", lambda _settings: FIXED_NOW)


@pytest.fixture()
def db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = TestingSession()
    import json

    with open(SEED_FILE, encoding="utf-8") as f:
        seed_business(session, json.load(f))
    session.add(Admin(username="admin", password=hash_password("admin123"), name="Admin", role="admin"))
    session.add(Admin(username="staff", password=hash_password("staff12345"), name="Staff", role="staff"))
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def client(db, monkeypatch):
    def override():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    monkeypatch.setattr(database, "SessionLocal", TestingSession)
    app.dependency_overrides[get_db] = override
    limiter.reset()
    llm_client.set_llm_client(None)
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    llm_client.set_llm_client(None)


def login(client, username="admin", password="admin123") -> dict:
    res = client.post("/api/admin/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['token']}"}


@pytest.fixture()
def admin_headers(client):
    return login(client)


@pytest.fixture()
def staff_headers(client):
    return login(client, "staff", "staff12345")


TUESDAY = FIXED_NOW.date() + timedelta(days=1)
SUNDAY = FIXED_NOW.date() + timedelta(days=6)
