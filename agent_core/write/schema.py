"""WriteProposal — the structured, human-confirmable draft the LLM produces.

The LLM never mutates data; it only fills this shape, which a human approves and an
executor (LLM-free) commits. ``params_hash`` + ``manifest_digest`` bind an approval to
exactly what was shown. Full M3b binding (target ETag, effect-policy version, richer
status) is reserved — see ROADMAP M3b.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from pydantic import BaseModel, Field


def canonical_params_hash(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class WriteProposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    deployment_id: str
    manifest_digest: str
    subject: str                       # actor who proposed (and who must confirm)
    tool: str                          # the side-effecting tool to execute on confirm
    params: dict = Field(default_factory=dict)
    diff: str = ""                     # human-readable preview of the change
    idempotency_key: str = ""          # defaults to proposal_id if unset

    def params_hash(self) -> str:
        return canonical_params_hash(self.params)

    def with_defaults(self) -> "WriteProposal":
        if not self.idempotency_key:
            return self.model_copy(update={"idempotency_key": self.proposal_id})
        return self
