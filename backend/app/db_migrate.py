"""Runs Alembic migrations on startup.

Databases created before migrations existed (tables made by create_all, no alembic_version
table) are stamped with the baseline revision first, so their tables and data are kept.

Manual use:  alembic upgrade head   (from the backend folder)
"""
import logging
import os
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import OperationalError

from .database import engine

logger = logging.getLogger("ava.migrate")

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BASELINE_REVISION = "0001"


def _config(connection) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    cfg.attributes["connection"] = connection
    cfg.attributes["skip_logging_config"] = True
    return cfg


def _wait_for_database(retries: int, delay: float) -> None:
    """MySQL may still be starting: retry only the connection, never the migration itself."""
    for attempt in range(1, retries + 1):
        try:
            with engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            return
        except OperationalError:
            if attempt == retries:
                raise
            logger.info("Database not reachable yet (attempt %d/%d), retrying...", attempt, retries)
            time.sleep(delay)


def run_migrations(retries: int = 15, delay: float = 2.0) -> None:
    _wait_for_database(retries, delay)
    with engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        cfg = _config(connection)
        if "alembic_version" not in tables and "admins" in tables:
            logger.info("Existing database without migration history: stamping baseline %s", BASELINE_REVISION)
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")
    logger.info("Database schema is up to date")
