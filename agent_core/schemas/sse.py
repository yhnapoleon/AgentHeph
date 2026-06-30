"""SSE contract (M0, ``v1alpha1``).

Request carries only ``deployment_id`` (server resolves the immutable
manifest_digest — clients never pick the running version). Every event shares one
envelope with ``run_id`` (one turn), ``thread_id`` (whole conversation), and a
server-assigned ``seq`` (the authoritative ordering — ``timestamp`` is for
observability only). ``call_id`` pairs tool_call/tool_result (fixes pairing by
name, which breaks under parallel calls).
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

SSE_SCHEMA_VERSION = "1"


class ChatRequest(BaseModel):
    deployment_id: str
    message: str = Field(min_length=1, max_length=8000)
    thread_id: str | None = Field(default=None, max_length=64)
    client_request_id: str | None = None


class EventType(str, Enum):
    meta = "meta"
    tool_call = "tool_call"
    tool_result = "tool_result"
    artifact = "artifact"
    answer = "answer"
    error = "error"
    done = "done"
    # reserved — phase-2 write path; defined for forward-compat, not emitted by guide
    write_proposal = "write_proposal"
    proposal_status = "proposal_status"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventEnvelope(BaseModel):
    schema_version: str = SSE_SCHEMA_VERSION
    event: EventType
    run_id: str
    thread_id: str
    seq: int
    timestamp: str = Field(default_factory=_now_iso)
    data: dict = Field(default_factory=dict)


# --- documented data shapes for common events (validation + reference) ---
class ToolCallData(BaseModel):
    call_id: str
    tool: str
    args_preview: dict = Field(default_factory=dict)


class ToolResultData(BaseModel):
    call_id: str
    tool: str
    preview: str = ""
