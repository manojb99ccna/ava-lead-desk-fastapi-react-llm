"""Idempotent seeding. Each part only runs when its table is empty, so real data is never overwritten.

- Default admin from ADMIN_USERNAME / ADMIN_PASSWORD (only if there are no users yet).
- Sample business data from backend/seed/seed_data.json.

Run manually:  python -m app.seed
"""
import json
import logging
import os
from datetime import time

from sqlalchemy.orm import Session

from .auth import hash_password
from .core.config import settings
from .database import SessionLocal
from .models import (
    ROLE_ADMIN,
    Admin,
    AvaBusinessFAQ,
    AvaBusinessSetting,
    AvaBusinessWorkingHour,
    AvaService,
    AvaSysIntent,
    AvaSysIntentTrainingExample,
)

logger = logging.getLogger("ava.seed")

SEED_FILE = os.path.join(os.path.dirname(__file__), "..", "seed", "seed_data.json")


def _t(value):
    return time.fromisoformat(value) if value else None


def seed_admin(db: Session) -> bool:
    if db.query(Admin.id).first():
        return False
    if not settings.admin_username or not settings.admin_password:
        logger.warning("No admin users exist and ADMIN_USERNAME/ADMIN_PASSWORD are not set.")
        return False
    db.add(Admin(username=settings.admin_username, password=hash_password(settings.admin_password),
                 name="Administrator", role=ROLE_ADMIN, is_active=True))
    logger.info("Created default admin user '%s'", settings.admin_username)
    return True


def seed_business(db: Session, data: dict) -> list[str]:
    done = []
    if not db.query(AvaBusinessSetting.id).first() and data.get("business"):
        db.add(AvaBusinessSetting(**data["business"]))
        done.append("business settings")
    if not db.query(AvaBusinessWorkingHour.id).first():
        for row in data.get("working_hours", []):
            db.add(AvaBusinessWorkingHour(day_of_week=row["day_of_week"], is_open=row["is_open"],
                                          opening_time=_t(row.get("opening_time")),
                                          closing_time=_t(row.get("closing_time"))))
        done.append("working hours")
    if not db.query(AvaService.id).first():
        for row in data.get("services", []):
            db.add(AvaService(**row, is_active=True))
        done.append("services")
    if not db.query(AvaBusinessFAQ.id).first():
        for row in data.get("faqs", []):
            db.add(AvaBusinessFAQ(**row, is_active=True))
        done.append("FAQs")
    if not db.query(AvaSysIntent.id).first():
        for name, examples in data.get("intents", {}).items():
            intent = AvaSysIntent(name=name, is_active=True)
            db.add(intent)
            db.flush()
            for text in examples:
                db.add(AvaSysIntentTrainingExample(intent_id=intent.id, text=text, is_active=True))
        done.append("intents")
    return done


def run_seed(db: Session | None = None) -> None:
    own = db is None
    db = db or SessionLocal()
    try:
        seed_admin(db)
        try:
            with open(SEED_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            logger.warning("Seed file %s not found or invalid; skipping sample data.", SEED_FILE)
            data = {}
        done = seed_business(db, data)
        db.commit()
        if done:
            logger.info("Seeded sample data: %s", ", ".join(done))
    except Exception:
        db.rollback()
        logger.exception("Seeding failed")
        raise
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    run_seed()
