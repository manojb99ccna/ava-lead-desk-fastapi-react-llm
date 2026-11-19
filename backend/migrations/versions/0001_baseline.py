"""Baseline: the schema as it existed before migrations (created by Base.metadata.create_all).

Existing databases are only *stamped* with this revision (see app/db_migrate.py); for a new,
empty database it creates the original tables.

Revision ID: 0001
Revises:
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps(updated=True):
    cols = [sa.Column("created_at", sa.DateTime(), server_default=sa.func.now())]
    if updated:
        cols.append(sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    return cols


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("password", sa.String(32), nullable=False),
        sa.Column("name", sa.String(100)),
        *_timestamps(updated=False),
    )
    op.create_table(
        "ava_sys_intents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.String(255)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "ava_sys_intent_training_examples",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("intent_id", sa.Integer(),
                  sa.ForeignKey("ava_sys_intents.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_table(
        "ava_leads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100)),
        sa.Column("phone", sa.String(30)),
        sa.Column("email", sa.String(255)),
        sa.Column("requested_service", sa.String(255)),
        sa.Column("preferred_datetime", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        *_timestamps(updated=False),
    )
    op.create_index("ix_ava_leads_id", "ava_leads", ["id"])
    op.create_table(
        "ava_conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False, unique=True),
        sa.Column("intent", sa.String(50)),
        sa.Column("current_step", sa.String(50)),
        sa.Column("lead_data", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_ava_conversations_id", "ava_conversations", ["id"])
    op.create_table(
        "ava_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("ava_conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sender", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        *_timestamps(updated=False),
    )
    op.create_index("ix_ava_messages_id", "ava_messages", ["id"])
    op.create_index("ix_ava_messages_conversation_id", "ava_messages", ["conversation_id"])
    op.create_table(
        "ava_business_faqs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("intent", sa.String(50), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_ava_business_faqs_id", "ava_business_faqs", ["id"])
    op.create_index("ix_ava_business_faqs_intent", "ava_business_faqs", ["intent"])
    op.create_table(
        "ava_appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("service", sa.String(255)),
        sa.Column("appointment_date", sa.DateTime(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("source", sa.String(50), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_ava_appointments_id", "ava_appointments", ["id"])
    op.create_index("ix_ava_appointments_appointment_date", "ava_appointments", ["appointment_date"])
    op.create_table(
        "ava_business_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("appointment_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("booking_window_days", sa.Integer(), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_ava_business_settings_id", "ava_business_settings", ["id"])
    op.create_table(
        "ava_business_working_hours",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_of_week", sa.Integer(), nullable=False, unique=True),
        sa.Column("is_open", sa.Boolean(), nullable=False),
        sa.Column("opening_time", sa.Time()),
        sa.Column("closing_time", sa.Time()),
        *_timestamps(),
    )
    op.create_index("ix_ava_business_working_hours_id", "ava_business_working_hours", ["id"])


def downgrade() -> None:
    for table in ("ava_business_working_hours", "ava_business_settings", "ava_appointments", "ava_business_faqs",
                  "ava_messages", "ava_conversations", "ava_leads", "ava_sys_intent_training_examples",
                  "ava_sys_intents", "admins"):
        op.drop_table(table)
