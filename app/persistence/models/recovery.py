import uuid
from sqlalchemy import CheckConstraint, Column, String, DateTime, Numeric, Enum as SQLEnum, Integer, text, ForeignKey, Index, UniqueConstraint, text as sql_text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.persistence.models.base import Base
from app.domain.recovery.states import RecoveryState, AttemptState, JobState

class RecoveryCase(Base):
    __tablename__ = "recovery_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    amount_at_risk = Column(Numeric(precision=12, scale=4), nullable=False)
    currency = Column(String(3), nullable=False)
    status = Column(SQLEnum(RecoveryState, name="recovery_state_enum"), nullable=False)
    failure_reason = Column(String, nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, nullable=False)
    started_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False)
    last_action_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), onupdate=sql_text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint('amount_at_risk >= 0', name='chk_recovery_case_amount_positive'),
        Index(
            "ix_active_recovery_case_per_payment",
            "payment_id",
            unique=True,
            postgresql_where=sql_text("status NOT IN ('RECOVERED', 'ESCALATED', 'STOPPED')")
        ),
    )

class RecoveryAttempt(Base):
    __tablename__ = "recovery_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recovery_case_id = Column(UUID(as_uuid=True), ForeignKey("recovery_cases.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    action_type = Column(String, nullable=False)
    status = Column(SQLEnum(AttemptState, name="attempt_state_enum"), nullable=False)
    scheduled_for = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failure_reason = Column(String, nullable=True)
    result_code = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        UniqueConstraint("recovery_case_id", "attempt_number", name="uq_recovery_attempt_number"),
    )

class RecoveryDecision(Base):
    __tablename__ = "recovery_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recovery_case_id = Column(UUID(as_uuid=True), ForeignKey("recovery_cases.id"), nullable=False)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("recovery_attempts.id"), nullable=True)
    decision_source = Column(String, nullable=False) # AI, RULE, FALLBACK
    action_type = Column(String, nullable=False)
    parameters_json = Column(JSONB, nullable=False)
    reason = Column(String, nullable=False)
    policy_result = Column(String, nullable=False)
    model_name = Column(String, nullable=True)
    prompt_version = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False)

class RecoveryJob(Base):
    __tablename__ = "recovery_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recovery_case_id = Column(UUID(as_uuid=True), ForeignKey("recovery_cases.id"), nullable=False)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("recovery_attempts.id"), nullable=True)
    job_type = Column(String, nullable=False)
    status = Column(SQLEnum(JobState, name="job_state_enum"), nullable=False)
    scheduled_for = Column(DateTime, nullable=False)
    available_at = Column(DateTime, nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, nullable=False)
    locked_at = Column(DateTime, nullable=True)
    locked_by = Column(String, nullable=True)
    last_error = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), nullable=False)
    updated_at = Column(DateTime, server_default=sql_text("CURRENT_TIMESTAMP"), onupdate=sql_text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        Index("ix_recovery_jobs_poll", "status", "available_at"),
    )


