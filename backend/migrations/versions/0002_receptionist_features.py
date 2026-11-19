"""Receptionist features: roles, customers, services, booking codes, history, handoffs.

Only adds columns, tables, indexes and foreign keys. Existing rows are kept; existing
appointments get a generated booking code.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06
"""
import secrets

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# MySQL cannot roll back DDL, so a failed run can leave part of this migration applied.
# These helpers make every step skip work that already exists, so the migration can be re-run.
def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table):
    return _insp().has_table(table)


def _has_column(table, column):
    return any(c["name"] == column for c in _insp().get_columns(table))


def _has_index(table, name):
    insp = _insp()
    return any(i["name"] == name for i in insp.get_indexes(table)) or         any(u["name"] == name for u in insp.get_unique_constraints(table))


def _has_fk(table, name):
    return any(fk["name"] == name for fk in _insp().get_foreign_keys(table))


def add_column(table, column):
    if not _has_column(table, column.name):
        op.add_column(table, column)


def create_index(name, table, columns, **kw):
    if not _has_index(table, name):
        op.create_index(name, table, columns, **kw)


def create_foreign_key(name, source, referent, local_cols, remote_cols, **kw):
    if not _has_fk(source, name):
        op.create_foreign_key(name, source, referent, local_cols, remote_cols, **kw)


def create_table(name, *columns):
    if not _has_table(name):
        op.create_table(name, *columns)


def _ts():
    return [sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now())]


def upgrade() -> None:
    # --- users / roles -------------------------------------------------------
    password_col = next(c for c in _insp().get_columns("admins") if c["name"] == "password")
    if (getattr(password_col["type"], "length", None) or 255) < 255:
        op.alter_column("admins", "password", existing_type=sa.String(32), type_=sa.String(255),
                        existing_nullable=False)
    add_column("admins", sa.Column("role", sa.String(20), nullable=False, server_default="admin"))
    add_column("admins", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    add_column("admins", sa.Column("last_login_at", sa.DateTime(), nullable=True))
    add_column("admins", sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))

    # --- intent training data -------------------------------------------------
    add_column("ava_sys_intent_training_examples",
                  sa.Column("source", sa.String(20), nullable=False, server_default="manual"))
    create_index("ix_ava_sys_intent_training_examples_source", "ava_sys_intent_training_examples", ["source"])

    # --- new tables -----------------------------------------------------------
    create_table(
        "ava_customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100)),
        sa.Column("phone", sa.String(30), nullable=False, unique=True),
        sa.Column("email", sa.String(255)),
        *_ts(),
    )
    create_index("ix_ava_customers_id", "ava_customers", ["id"])

    create_table(
        "ava_services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("description", sa.Text()),
        sa.Column("price", sa.String(100)),
        sa.Column("duration_minutes", sa.Integer()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_ts(),
    )
    create_index("ix_ava_services_id", "ava_services", ["id"])

    # --- business settings ------------------------------------------------------
    for name, type_ in (("business_name", sa.String(150)), ("description", sa.Text()), ("phone", sa.String(50)),
                        ("email", sa.String(255)), ("address", sa.String(255)), ("website", sa.String(255))):
        add_column("ava_business_settings", sa.Column(name, type_, nullable=True))

    # --- conversations -----------------------------------------------------------
    add_column("ava_conversations", sa.Column("status", sa.String(20), nullable=False, server_default="active"))
    add_column("ava_conversations", sa.Column("engine", sa.String(20), nullable=True))
    add_column("ava_conversations", sa.Column("channel", sa.String(20), nullable=False, server_default="web"))
    create_index("ix_ava_conversations_channel", "ava_conversations", ["channel"])
    add_column("ava_conversations", sa.Column("customer_id", sa.Integer(), nullable=True))
    create_index("ix_ava_conversations_customer_id", "ava_conversations", ["customer_id"])
    create_foreign_key("fk_conversations_customer", "ava_conversations", "ava_customers", ["customer_id"], ["id"],
                          ondelete="SET NULL")
    create_index("ix_ava_messages_conversation_created", "ava_messages", ["conversation_id", "created_at"])

    # --- leads -------------------------------------------------------------------
    add_column("ava_leads", sa.Column("message", sa.Text(), nullable=True))
    add_column("ava_leads", sa.Column("notes", sa.Text(), nullable=True))
    add_column("ava_leads", sa.Column("customer_id", sa.Integer(), nullable=True))
    add_column("ava_leads", sa.Column("conversation_id", sa.Integer(), nullable=True))
    add_column("ava_leads", sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    create_index("ix_ava_leads_status", "ava_leads", ["status"])
    create_index("ix_ava_leads_customer_id", "ava_leads", ["customer_id"])
    create_index("ix_ava_leads_conversation_id", "ava_leads", ["conversation_id"])
    create_foreign_key("fk_leads_customer", "ava_leads", "ava_customers", ["customer_id"], ["id"],
                          ondelete="SET NULL")
    create_foreign_key("fk_leads_conversation", "ava_leads", "ava_conversations", ["conversation_id"], ["id"],
                          ondelete="SET NULL")

    # --- appointments --------------------------------------------------------------
    add_column("ava_appointments", sa.Column("booking_code", sa.String(16), nullable=True))
    add_column("ava_appointments", sa.Column("customer_id", sa.Integer(), nullable=True))
    add_column("ava_appointments", sa.Column("conversation_id", sa.Integer(), nullable=True))
    add_column("ava_appointments", sa.Column("cancelled_at", sa.DateTime(), nullable=True))

    conn = op.get_bind()
    used = set()
    for (appointment_id,) in conn.execute(sa.text("SELECT id FROM ava_appointments WHERE booking_code IS NULL")):
        code = None
        while code is None or code in used:
            code = "AVA-" + "".join(secrets.choice(_ALPHABET) for _ in range(6))
        used.add(code)
        conn.execute(sa.text("UPDATE ava_appointments SET booking_code = :c WHERE id = :i"),
                     {"c": code, "i": appointment_id})

    create_index("uq_ava_appointments_booking_code", "ava_appointments", ["booking_code"], unique=True)
    create_index("ix_ava_appointments_status", "ava_appointments", ["status"])
    create_index("ix_ava_appointments_customer_id", "ava_appointments", ["customer_id"])
    create_index("ix_ava_appointments_conversation_id", "ava_appointments", ["conversation_id"])
    create_foreign_key("fk_appointments_customer", "ava_appointments", "ava_customers", ["customer_id"], ["id"],
                          ondelete="SET NULL")
    create_foreign_key("fk_appointments_conversation", "ava_appointments", "ava_conversations",
                          ["conversation_id"], ["id"], ondelete="SET NULL")

    create_table(
        "ava_appointment_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("appointment_id", sa.Integer(), sa.ForeignKey("ava_appointments.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("old_appointment_date", sa.DateTime()),
        sa.Column("new_appointment_date", sa.DateTime()),
        sa.Column("old_status", sa.String(30)),
        sa.Column("new_status", sa.String(30)),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    create_index("ix_ava_appointment_history_id", "ava_appointment_history", ["id"])
    create_index("ix_ava_appointment_history_appointment_id", "ava_appointment_history", ["appointment_id"])

    # --- human handoff ----------------------------------------------------------------
    create_table(
        "ava_handoff_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("ava_conversations.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("ava_customers.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(100)),
        sa.Column("phone", sa.String(30)),
        sa.Column("email", sa.String(255)),
        sa.Column("reason", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("assigned_to", sa.String(50)),
        sa.Column("resolution_note", sa.Text()),
        *_ts(),
    )
    create_index("ix_ava_handoff_requests_id", "ava_handoff_requests", ["id"])
    create_index("ix_ava_handoff_requests_conversation_id", "ava_handoff_requests", ["conversation_id"])
    create_index("ix_ava_handoff_requests_customer_id", "ava_handoff_requests", ["customer_id"])
    create_index("ix_ava_handoff_requests_status", "ava_handoff_requests", ["status"])


def downgrade() -> None:
    op.drop_table("ava_handoff_requests")
    op.drop_table("ava_appointment_history")
    for fk in ("fk_appointments_conversation", "fk_appointments_customer"):
        op.drop_constraint(fk, "ava_appointments", type_="foreignkey")
    for ix in ("ix_ava_appointments_conversation_id", "ix_ava_appointments_customer_id", "ix_ava_appointments_status",
               "uq_ava_appointments_booking_code"):
        op.drop_index(ix, table_name="ava_appointments")
    for col in ("cancelled_at", "conversation_id", "customer_id", "booking_code"):
        op.drop_column("ava_appointments", col)
    for fk in ("fk_leads_conversation", "fk_leads_customer"):
        op.drop_constraint(fk, "ava_leads", type_="foreignkey")
    for ix in ("ix_ava_leads_conversation_id", "ix_ava_leads_customer_id", "ix_ava_leads_status"):
        op.drop_index(ix, table_name="ava_leads")
    for col in ("updated_at", "conversation_id", "customer_id", "notes", "message"):
        op.drop_column("ava_leads", col)
    op.drop_index("ix_ava_messages_conversation_created", table_name="ava_messages")
    op.drop_constraint("fk_conversations_customer", "ava_conversations", type_="foreignkey")
    op.drop_index("ix_ava_conversations_customer_id", table_name="ava_conversations")
    op.drop_index("ix_ava_conversations_channel", table_name="ava_conversations")
    for col in ("customer_id", "channel", "engine", "status"):
        op.drop_column("ava_conversations", col)
    for col in ("website", "address", "email", "phone", "description", "business_name"):
        op.drop_column("ava_business_settings", col)
    op.drop_table("ava_services")
    op.drop_table("ava_customers")
    op.drop_index("ix_ava_sys_intent_training_examples_source", table_name="ava_sys_intent_training_examples")
    op.drop_column("ava_sys_intent_training_examples", "source")
    for col in ("updated_at", "last_login_at", "is_active", "role"):
        op.drop_column("admins", col)
    op.alter_column("admins", "password", existing_type=sa.String(255), type_=sa.String(32), existing_nullable=False)
