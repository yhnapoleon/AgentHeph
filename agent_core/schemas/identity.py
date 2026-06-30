"""Identity model (M0 contract).

Split into three concerns so none becomes a god-object (per Codex review):
  * Principal          — who is asking (guide uses this).
  * CredentialContext  — how the runtime authenticates to downstream tools/APIs
                         (placeholder in M0; real impl in M3-foundation:
                         service-account vs delegated token, audience binding,
                         no token passthrough — reuse MCP OAuth, do not self-build).
  * ExecutionContext   — per-run binding (set at turn start).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CredentialMode(str, Enum):
    service_account = "service_account"
    delegated_user = "delegated_user"


class Principal(BaseModel):
    """Who is making the request. Guide uses issuer/subject/roles/scopes;
    ``tenant_id`` is reserved for multi-tenant (phase 2)."""

    issuer: str
    subject: str
    tenant_id: str | None = None  # reserved (phase 2)
    roles: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)


class CredentialContext(BaseModel):
    """How the runtime authenticates to downstream tools/APIs.

    Reserved/placeholder in M0. M3-foundation implements: service_account vs
    delegated_user, audience/resource binding, scope minimization + step-up,
    and the hard rule that tokens are never passed through to a server they are
    not audience-bound to. ``token_ref`` points into the secret store — never
    an inline credential.
    """

    mode: CredentialMode = CredentialMode.service_account
    audience: str | None = None
    delegated: bool = False
    token_ref: str | None = None


class ExecutionContext(BaseModel):
    """Per-run context, bound at turn start. ``manifest_digest`` is resolved
    server-side from ``deployment_id`` (clients never choose the running version)."""

    deployment_id: str
    manifest_digest: str
    run_id: str
    thread_id: str
