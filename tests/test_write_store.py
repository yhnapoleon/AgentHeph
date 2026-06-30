"""M1.3: the write store is consistency-correct where BAU's confirm path was not.

Key acceptance (ROADMAP): on an injected execution failure the proposal is never lost —
it lands in RECONCILIATION_REQUIRED with the intent + idempotency_key preserved, and a
retry uses the SAME idempotency_key (effectively-once). Plus: concurrent claims execute
once, ownership/expiry/reject enforced."""
from __future__ import annotations

import pytest

pytest.importorskip("sqlalchemy")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from agent_core.write import (  # noqa: E402
    Base,
    OutboxRow,
    OutboxStatus,
    ProposalStatus,
    WriteNotApplied,
    WriteProposal,
    claim,
    confirm,
    create,
    execute_claimed,
    get,
    reject,
    retry_reconciliation,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _proposal(**kw) -> WriteProposal:
    base = dict(deployment_id="demo", manifest_digest="sha256:x", subject="alice",
                tool="close_ticket", params={"ticket_id": 1}, diff="close #1")
    base.update(kw)
    return WriteProposal(**base)


def test_happy_path_succeeds_and_records_result(session):
    pid = create(session, _proposal())
    seen = []
    def executor(tool, params, idem):
        seen.append((tool, params, idem))
        return {"closed": params["ticket_id"]}

    reason, status = confirm(session, pid, subject="alice", executor=executor)
    assert reason == "ok" and status == ProposalStatus.SUCCEEDED.value
    row = get(session, pid)
    assert row.result_json == {"closed": 1}
    # idempotency_key defaults to the proposal_id and is passed to the executor.
    assert seen[0][2] == pid


def test_injected_failure_is_reconcilable_not_lost(session):
    pid = create(session, _proposal())
    calls = []
    def flaky(tool, params, idem):
        calls.append(idem)
        raise RuntimeError("downstream timeout")  # unknown outcome

    reason, status = confirm(session, pid, subject="alice", executor=flaky)
    assert reason == "ok"
    assert status == ProposalStatus.RECONCILIATION_REQUIRED.value
    # not lost: the proposal and its outbox intent survive, with the idempotency key.
    row = get(session, pid)
    assert row.status == ProposalStatus.RECONCILIATION_REQUIRED.value
    ob = session.query(OutboxRow).filter_by(proposal_id=pid).one()
    assert ob.status == OutboxStatus.RECONCILIATION_REQUIRED.value
    assert ob.idempotency_key == pid

    # retry succeeds and reuses the SAME idempotency key (effectively-once downstream).
    def now_ok(tool, params, idem):
        calls.append(idem)
        return {"closed": params["ticket_id"]}
    final = retry_reconciliation(session, pid, now_ok)
    assert final == ProposalStatus.SUCCEEDED.value
    assert calls == [pid, pid]                        # same key both attempts
    assert get(session, pid).result_json == {"closed": 1}


def test_write_not_applied_is_terminal_failed(session):
    pid = create(session, _proposal())
    def refuses(tool, params, idem):
        raise WriteNotApplied("precondition failed")  # definitely no effect
    reason, status = confirm(session, pid, subject="alice", executor=refuses)
    assert status == ProposalStatus.FAILED.value
    ob = session.query(OutboxRow).filter_by(proposal_id=pid).one()
    assert ob.status == OutboxStatus.DONE.value        # nothing to reconcile


def test_concurrent_claim_executes_once(session):
    pid = create(session, _proposal())
    row1, r1 = claim(session, pid, subject="alice")
    row2, r2 = claim(session, pid, subject="alice")    # second claim loses the CAS
    assert r1 == "ok" and row1 is not None
    assert r2 == "conflict" and row2 is None
    assert get(session, pid).status == ProposalStatus.EXECUTING.value
    # exactly one outbox intent was written.
    assert session.query(OutboxRow).filter_by(proposal_id=pid).count() == 1
    execute_claimed(session, pid, lambda t, p, i: {"ok": True})
    assert get(session, pid).status == ProposalStatus.SUCCEEDED.value


def test_wrong_subject_is_forbidden(session):
    pid = create(session, _proposal(subject="alice"))
    row, reason = claim(session, pid, subject="bob")
    assert reason == "forbidden" and row is None
    assert get(session, pid).status == ProposalStatus.PENDING_APPROVAL.value


def test_expired_proposal_cannot_be_claimed(session):
    pid = create(session, _proposal(), ttl_seconds=-1)  # already expired
    row, reason = claim(session, pid, subject="alice")
    assert reason == "expired" and row is None
    assert get(session, pid).status == ProposalStatus.EXPIRED.value


def test_reject_blocks_claim(session):
    pid = create(session, _proposal())
    assert reject(session, pid, subject="alice") is True
    row, reason = claim(session, pid, subject="alice")
    assert reason == "conflict" and row is None
    assert get(session, pid).status == ProposalStatus.REJECTED.value
