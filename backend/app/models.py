from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    func,
)

from .database import Base
from .db_types import UTCDateTime

# ---------------------------------------------------------------------------
# Users (admin panel). The table keeps its original name "admins".
# ---------------------------------------------------------------------------

ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLES = (ROLE_ADMIN, ROLE_STAFF)


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    # Argon2id hash. Legacy rows may still hold a 32-char MD5 digest until next login.
    password = Column(String(255), nullable=False)
    name = Column(String(100))
    role = Column(String(20), nullable=False, default=ROLE_ADMIN, server_default=ROLE_ADMIN)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    last_login_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Intent classifier training data
# ---------------------------------------------------------------------------


class AvaSysIntent(Base):
    __tablename__ = "ava_sys_intents"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(String(255))
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class AvaSysIntentTrainingExample(Base):
    __tablename__ = "ava_sys_intent_training_examples"

    id = Column(Integer, primary_key=True)
    intent_id = Column(
        Integer,
        ForeignKey("ava_sys_intents.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    text = Column(Text, nullable=False)
    # "manual" = added by a person (weighted higher in training), "generated" = generate_intent_data.py
    source = Column(String(20), nullable=False, default="manual", server_default="manual", index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------


class AvaCustomer(Base):
    __tablename__ = "ava_customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    # Digits only (normalized), used to match returning customers.
    phone = Column(String(30), nullable=False, unique=True)
    email = Column(String(255), nullable=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Leads
# ---------------------------------------------------------------------------

LEAD_STATUSES = ("new", "contacted", "qualified", "converted", "lost")


class AvaLead(Base):
    __tablename__ = "ava_leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(255), nullable=True)
    requested_service = Column(String(255), nullable=True)
    preferred_datetime = Column(String(100), nullable=True)
    message = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="new", index=True)
    source = Column(String(50), nullable=False, default="website_chat")
    customer_id = Column(Integer, ForeignKey("ava_customers.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("ava_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

CONVERSATION_STATUSES = ("active", "handoff", "closed")
CHANNELS = ("web", "whatsapp", "voice")


class AvaConversation(Base):
    __tablename__ = "ava_conversations"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False)
    intent = Column(String(50), nullable=True)
    current_step = Column(String(50), nullable=True)
    lead_data = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="active", server_default="active")
    engine = Column(String(20), nullable=True)  # "llm" or "rules": who produced the last reply
    # Where the customer is talking to Ava: web (chat widget), whatsapp or voice (phone call).
    channel = Column(String(20), nullable=False, default="web", server_default="web", index=True)
    customer_id = Column(Integer, ForeignKey("ava_customers.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class AvaMessage(Base):
    __tablename__ = "ava_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("ava_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender = Column(String(20), nullable=False)  # user or ava
    message = Column(Text, nullable=False)
    created_at = Column(UTCDateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Business knowledge
# ---------------------------------------------------------------------------


class AvaBusinessFAQ(Base):
    __tablename__ = "ava_business_faqs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    intent = Column(String(50), index=True, nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class AvaService(Base):
    __tablename__ = "ava_services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    # Free text so the business controls wording, e.g. "From INR 15,000" or "On request".
    price = Column(String(100), nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="1")
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class AvaBusinessSetting(Base):
    __tablename__ = "ava_business_settings"

    id = Column(Integer, primary_key=True, index=True)
    business_name = Column(String(150), nullable=True)
    description = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(String(255), nullable=True)
    website = Column(String(255), nullable=True)
    timezone = Column(String(100), nullable=False, default="Asia/Kolkata")
    appointment_duration_minutes = Column(Integer, nullable=False, default=60)
    booking_window_days = Column(Integer, nullable=False, default=7)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class AvaBusinessWorkingHour(Base):
    __tablename__ = "ava_business_working_hours"

    id = Column(Integer, primary_key=True, index=True)
    day_of_week = Column(Integer, nullable=False, unique=True)  # 0 = Monday
    is_open = Column(Boolean, nullable=False, default=True)
    opening_time = Column(Time, nullable=True)
    closing_time = Column(Time, nullable=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


# ---------------------------------------------------------------------------
# Appointments
# ---------------------------------------------------------------------------

APPOINTMENT_STATUSES = ("pending", "confirmed", "completed", "cancelled", "no_show")
BLOCKING_STATUSES = ("pending", "confirmed")


class AvaAppointment(Base):
    __tablename__ = "ava_appointments"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String(16), nullable=True, unique=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(30), nullable=False)
    email = Column(String(255), nullable=True)
    service = Column(String(255), nullable=True)
    appointment_date = Column(DateTime, nullable=False, index=True)
    duration_minutes = Column(Integer, nullable=False, default=60)
    status = Column(String(30), nullable=False, default="pending", index=True)
    notes = Column(Text, nullable=True)
    source = Column(String(50), nullable=False, default="website_chat")
    customer_id = Column(Integer, ForeignKey("ava_customers.id", ondelete="SET NULL"), nullable=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("ava_conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cancelled_at = Column(DateTime, nullable=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


class AvaAppointmentHistory(Base):
    __tablename__ = "ava_appointment_history"

    id = Column(Integer, primary_key=True, index=True)
    appointment_id = Column(
        Integer, ForeignKey("ava_appointments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action = Column(String(30), nullable=False)  # created, rescheduled, cancelled, status_changed, updated
    old_appointment_date = Column(DateTime, nullable=True)
    new_appointment_date = Column(DateTime, nullable=True)
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=True)
    actor = Column(String(100), nullable=False)  # "customer", "ava", or "admin:<username>"
    note = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, server_default=func.now())


# ---------------------------------------------------------------------------
# Human handoff
# ---------------------------------------------------------------------------

HANDOFF_STATUSES = ("open", "in_progress", "resolved")


class AvaHandoffRequest(Base):
    __tablename__ = "ava_handoff_requests"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("ava_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id = Column(Integer, ForeignKey("ava_customers.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(100), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(255), nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="open", server_default="open", index=True)
    assigned_to = Column(String(50), nullable=True)
    resolution_note = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, server_default=func.now())
    updated_at = Column(UTCDateTime, server_default=func.now(), onupdate=func.now())


Index("ix_ava_messages_conversation_created", AvaMessage.conversation_id, AvaMessage.created_at)
