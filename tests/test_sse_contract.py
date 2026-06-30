"""M0: SSE request/envelope contract, including call_id pairing data shapes."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_core.schemas.sse import (
    SSE_SCHEMA_VERSION,
    ChatRequest,
    EventEnvelope,
    EventType,
    ToolCallData,
    ToolResultData,
)


def test_chat_request_minimal():
    r = ChatRequest(deployment_id="bau-prod", message="hi")
    assert r.thread_id is None
    assert r.client_request_id is None


def test_chat_request_rejects_empty_and_overlong_message():
    with pytest.raises(ValidationError):
        ChatRequest(deployment_id="d", message="")
    with pytest.raises(ValidationError):
        ChatRequest(deployment_id="d", message="x" * 8001)


def test_event_envelope_defaults():
    ev = EventEnvelope(event=EventType.meta, run_id="r1", thread_id="t1", seq=0)
    assert ev.schema_version == SSE_SCHEMA_VERSION
    assert ev.timestamp  # auto-filled ISO timestamp
    assert ev.data == {}


def test_tool_call_result_pairing_by_call_id():
    call = ToolCallData(call_id="c-1", tool="app_knowledge", args_preview={"area": "issues"})
    result = ToolResultData(call_id="c-1", tool="app_knowledge", preview="...")
    # call_id is the pairing key (not the tool name) — survives parallel calls.
    assert call.call_id == result.call_id


def test_write_events_reserved_but_defined():
    # Defined for forward-compat; guide never emits them.
    assert EventType.write_proposal.value == "write_proposal"
    assert EventType.proposal_status.value == "proposal_status"
