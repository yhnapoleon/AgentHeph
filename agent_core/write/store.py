"""Consistency-correct proposal store (the M1.3 fix).

Guarantees, vs. BAU's confirm path:
  * **atomic claim** — PENDING_APPROVAL -> EXECUTING is a DB compare-and-set; under
    concurrency exactly one claim wins, the rest get ``conflict``. No "consume then
    lose if commit fails".
  * **transactional outbox** — the claim and the to-execute intent commit together, so
    a crash after claiming never loses the intent.
  * **effectively-once** — the executor gets a stable ``idempotency_key`` so a reconcile
    retry can't double-apply. No "commit then double on retry".
  * **single source of truth** — these rows; no second copy in a checkpoint.

All functions take an explicit ``session`` (unit-tests run on in-memory SQLite).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Callable

from sqlalchemy.orm import Session

from agent_core.write.models import (
    OutboxRow,
    OutboxStatus,
    ProposalStatus,
    WriteProposalRow,
    _utcnow,
)
from agent_core.write.schema import WriteProposal

DEFAULT_TTL_SECONDS = 900  # 15 minutes

# claim reason codes
CLAIM_OK = "ok"
CLAIM_NOT_FOUND = "not_found"
CLAIM_FORBIDDEN = "forbidden"     # token belongs to another actor
CLAIM_EXPIRED = "expired"
CLAIM_CONFLICT = "conflict"       # already claimed / rejected / not pending

# Executor signals the change DEFINITELY did not apply (safe terminal failure).
class WriteNotApplied(Exception):
    pass


# An executor performs the real side effect. It MUST use idempotency_key to dedupe
# downstream. Returns a JSON-able result dict.
Executor = Callable[[str, dict, str], dict]  # (tool, params, idempotency_key) -> result


def create(session: Session, proposal: WriteProposal, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Persist a freshly proposed (human-pending) write. Returns the proposal_id."""
    p = proposal.with_defaults()
    now = _utcnow()
    session.add(WriteProposalRow(
        proposal_id=p.proposal_id, deployment_id=p.deployment_id,
        manifest_digest=p.manifest_digest, subject=p.subject, tool=p.tool,
        params_json=p.params, params_hash=p.params_hash(), diff=p.diff,
        idempotency_key=p.idempotency_key,
        status=ProposalStatus.PENDING_APPROVAL.value,
        created_at=now, expires_at=now + timedelta(seconds=ttl_seconds),
    ))
    session.commit()
    return p.proposal_id


def get(session: Session, proposal_id: str) -> WriteProposalRow | None:
    return session.get(WriteProposalRow, proposal_id)


def reject(session: Session, proposal_id: str, *, subject: str) -> bool:
    """Owner rejects a pending proposal. Atomic CAS; True iff this call rejected it."""
    n = (
        session.query(WriteProposalRow)
        .filter(
            WriteProposalRow.proposal_id == proposal_id,
            WriteProposalRow.subject == subject,
            WriteProposalRow.status == ProposalStatus.PENDING_APPROVAL.value,
        )
        .update({WriteProposalRow.status: ProposalStatus.REJECTED.value,
                 WriteProposalRow.finalized_at: _utcnow()}, synchronize_session=False)
    )
    session.commit()
    return n == 1


def claim(session: Session, proposal_id: str, *, subject: str) -> tuple[WriteProposalRow | None, str]:
    """Atomically claim a pending proposal for execution.

    Checks ownership + expiry for a precise reason, then does the authoritative CAS
    (PENDING_APPROVAL -> EXECUTING). On success, writes the outbox intent in the SAME
    transaction. Returns (row | None, reason)."""
    row = session.get(WriteProposalRow, proposal_id)
    if row is None:
        return None, CLAIM_NOT_FOUND
    if row.subject != subject:
        return None, CLAIM_FORBIDDEN
    if row.expires_at is not None and _utcnow() >= row.expires_at:
        session.query(WriteProposalRow).filter(
            WriteProposalRow.proposal_id == proposal_id,
            WriteProposalRow.status == ProposalStatus.PENDING_APPROVAL.value,
        ).update({WriteProposalRow.status: ProposalStatus.EXPIRED.value}, synchronize_session=False)
        session.commit()
        return None, CLAIM_EXPIRED

    now = _utcnow()
    won = (
        session.query(WriteProposalRow)
        .filter(
            WriteProposalRow.proposal_id == proposal_id,
            WriteProposalRow.status == ProposalStatus.PENDING_APPROVAL.value,  # CAS guard
        )
        .update({WriteProposalRow.status: ProposalStatus.EXECUTING.value,
                 WriteProposalRow.claimed_at: now}, synchronize_session=False)
    )
    if won != 1:
        session.rollback()
        return None, CLAIM_CONFLICT
    # same transaction as the claim: the intent can never be lost after claiming.
    session.add(OutboxRow(
        proposal_id=proposal_id, idempotency_key=row.idempotency_key,
        intent_json={"tool": row.tool, "params": row.params_json},
        status=OutboxStatus.PENDING.value, created_at=now,
    ))
    session.commit()
    session.refresh(row)
    return row, CLAIM_OK


def _pending_outbox(session: Session, proposal_id: str) -> OutboxRow | None:
    return (
        session.query(OutboxRow)
        .filter(OutboxRow.proposal_id == proposal_id,
                OutboxRow.status.in_([OutboxStatus.PENDING.value,
                                      OutboxStatus.RECONCILIATION_REQUIRED.value]))
        .order_by(OutboxRow.id.desc())
        .first()
    )


def execute_claimed(session: Session, proposal_id: str, executor: Executor) -> str:
    """Run the side effect for a claimed (EXECUTING) proposal and finalize.

    success -> SUCCEEDED; ``WriteNotApplied`` -> FAILED (definitely no effect); any other
    exception -> RECONCILIATION_REQUIRED (outcome unknown; intent kept for reconcile).
    Returns the final ProposalStatus value."""
    row = session.get(WriteProposalRow, proposal_id)
    if row is None or row.status != ProposalStatus.EXECUTING.value:
        raise ValueError(f"proposal {proposal_id} is not in EXECUTING state")
    outbox = _pending_outbox(session, proposal_id)
    now = _utcnow()
    try:
        result = executor(row.tool, row.params_json, row.idempotency_key)
    except WriteNotApplied as exc:
        row.status = ProposalStatus.FAILED.value
        row.finalized_at = now
        row.result_json = {"error": str(exc), "applied": False}
        if outbox:
            outbox.status = OutboxStatus.DONE.value          # terminal: nothing to reconcile
            outbox.dispatched_at = now
        session.commit()
        return ProposalStatus.FAILED.value
    except Exception as exc:  # noqa: BLE001 - outcome unknown -> reconcile, never lose
        row.status = ProposalStatus.RECONCILIATION_REQUIRED.value
        row.finalized_at = now
        row.result_json = {"error": str(exc), "applied": "unknown"}
        if outbox:
            outbox.status = OutboxStatus.RECONCILIATION_REQUIRED.value
        session.commit()
        return ProposalStatus.RECONCILIATION_REQUIRED.value

    row.status = ProposalStatus.SUCCEEDED.value
    row.finalized_at = now
    row.result_json = result
    if outbox:
        outbox.status = OutboxStatus.DONE.value
        outbox.dispatched_at = now
        outbox.result_json = result
    session.commit()
    return ProposalStatus.SUCCEEDED.value


def confirm(session: Session, proposal_id: str, *, subject: str, executor: Executor) -> tuple[str, str]:
    """Claim + execute in one call (the common confirm path). Returns (reason, status)
    where reason is a CLAIM_* code and status is the final ProposalStatus (or '')."""
    _row, reason = claim(session, proposal_id, subject=subject)
    if reason != CLAIM_OK:
        return reason, ""
    return CLAIM_OK, execute_claimed(session, proposal_id, executor)


def retry_reconciliation(session: Session, proposal_id: str, executor: Executor) -> str:
    """Re-attempt a RECONCILIATION_REQUIRED proposal. CAS back to EXECUTING, then run the
    executor again with the SAME idempotency_key (so a previously-applied write is not
    double-applied). Returns the final ProposalStatus value."""
    won = (
        session.query(WriteProposalRow)
        .filter(
            WriteProposalRow.proposal_id == proposal_id,
            WriteProposalRow.status == ProposalStatus.RECONCILIATION_REQUIRED.value,  # CAS
        )
        .update({WriteProposalRow.status: ProposalStatus.EXECUTING.value,
                 WriteProposalRow.finalized_at: None}, synchronize_session=False)
    )
    session.commit()
    if won != 1:
        return CLAIM_CONFLICT
    return execute_claimed(session, proposal_id, executor)
