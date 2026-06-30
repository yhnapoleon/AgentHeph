"""SQLAlchemy tables for the write-proposal flow + its transactional outbox.

State machine (single source of truth = these rows; BAU does not use LangGraph
interrupt, so no checkpoint participates in write state):

    PENDING_APPROVAL --claim--> EXECUTING --ok--> SUCCEEDED
                                          --known-fail--> FAILED
                                          --unknown--> RECONCILIATION_REQUIRED
    PENDING_APPROVAL --reject--> REJECTED
    PENDING_APPROVAL --expire--> EXPIRED
    (DRAFT / CANCELLED reserved; full edit-mode extension is M3b)

The outbox row is written in the SAME transaction as the claim, so a crash after
claiming never loses the intent: it is replayable (idempotency_key makes the downstream
write effectively-once). This is the fix for BAU's confirm path, which consumed then
committed (lose-on-failure) against a store documented as commit-then-consume
(double-on-retry) — neither exactly-once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    # Naive UTC: the DateTime columns are timezone-naive (SQLite drops tzinfo), so we
    # keep one consistent convention to avoid aware/naive comparison errors.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    EXECUTING = "EXECUTING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    DONE = "DONE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class WriteProposalRow(Base):
    __tablename__ = "agent_write_proposals"

    proposal_id: Mapped[str] = mapped_column(String, primary_key=True)
    deployment_id: Mapped[str] = mapped_column(String)
    manifest_digest: Mapped[str] = mapped_column(String)
    subject: Mapped[str] = mapped_column(String)              # actor who proposed
    tool: Mapped[str] = mapped_column(String)
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    params_hash: Mapped[str] = mapped_column(String)         # binds approval to exact params
    diff: Mapped[str] = mapped_column(String, default="")    # human-readable preview
    idempotency_key: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default=ProposalStatus.PENDING_APPROVAL.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class OutboxRow(Base):
    __tablename__ = "agent_write_outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(String, index=True)
    idempotency_key: Mapped[str] = mapped_column(String)
    intent_json: Mapped[dict] = mapped_column(JSON, default=dict)   # {tool, params}
    status: Mapped[str] = mapped_column(String, default=OutboxStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
