"""M1 walking skeleton: manifest -> graph -> governed tools -> SSE, end to end, with a
scripted fake model. Asserts the call_id pairing fix and that per-row scope holds
through the real tool execution."""
from __future__ import annotations

import pathlib

import pytest

pytest.importorskip("langgraph")

from agent_core.manifest import compute_manifest_digest, load_manifest  # noqa: E402
from agent_core.runtime import InMemoryAuditSink, run_turn  # noqa: E402
from agent_core.schemas.identity import ExecutionContext, Principal  # noqa: E402
from agent_core.schemas.sse import EventType  # noqa: E402
from plugins.demo.providers import DemoAuth, DemoTools  # noqa: E402
from tests.fakes import FakeToolModel, final_msg, tool_call_msg  # noqa: E402

MANIFEST = (
    pathlib.Path(__file__).resolve().parent.parent / "plugins" / "demo" / "manifest.yaml"
)


def _execution(manifest) -> ExecutionContext:
    return ExecutionContext(
        deployment_id="demo", manifest_digest=compute_manifest_digest(manifest),
        run_id="run-1", thread_id="thread-1",
    )


def _run(principal, model, audit=None):
    manifest = load_manifest(MANIFEST)
    return list(run_turn(
        manifest=manifest, provider=DemoTools(), principal=principal,
        execution=_execution(manifest), message="which tickets are open?",
        model=model, auth_adapter=DemoAuth(), audit_sink=audit,
    ))


def test_contract_event_order_and_callid_pairing():
    model = FakeToolModel(responses=[
        tool_call_msg("list_tickets", {"status": "open"}, "call-xyz"),
        final_msg("You have 1 open ticket."),
    ])
    events = _run(Principal(issuer="t", subject="alice", roles=["member"]), model)

    kinds = [e.event for e in events]
    assert kinds[0] is EventType.meta
    assert kinds[-1] is EventType.done
    assert kinds.index(EventType.tool_call) < kinds.index(EventType.tool_result)
    assert kinds[-2] is EventType.answer  # answer is held until after tool events

    # seq is the authoritative, strictly increasing ordering.
    assert [e.seq for e in events] == list(range(len(events)))

    # the pairing fix: tool_result.call_id matches the tool_call.call_id (not the name).
    call = next(e for e in events if e.event is EventType.tool_call)
    result = next(e for e in events if e.event is EventType.tool_result)
    assert call.data["call_id"] == "call-xyz"
    assert result.data["call_id"] == "call-xyz"


def test_scope_holds_through_real_tool_execution():
    # alice asks for open tickets; the tool runs for real and must only see alice's rows.
    model = FakeToolModel(responses=[
        tool_call_msg("list_tickets", {"status": "open"}, "c1"),
        final_msg("done"),
    ])
    events = _run(Principal(issuer="t", subject="alice", roles=["member"]), model)
    result = next(e for e in events if e.event is EventType.tool_result)
    preview = result.data["preview"]
    assert "Login page 500" in preview     # alice's ticket #1 (open)
    assert "Webhook retries" not in preview  # bob's ticket #3 — must never appear
    assert "SSO timeout" not in preview      # bob's ticket #4


def test_audit_record_captures_turn():
    audit = InMemoryAuditSink()
    model = FakeToolModel(responses=[
        tool_call_msg("list_tickets", {"status": "open"}, "c1"),
        final_msg("You have 1 open ticket."),
    ])
    _run(Principal(issuer="t", subject="alice", roles=["member"]), model, audit=audit)
    assert len(audit.runs) == 1
    run = audit.runs[0]
    assert run.subject == "alice"
    assert "list_tickets" in run.tool_calls
    assert run.error is None
