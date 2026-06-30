"""Tool effect model (M0 contract), layered per Codex review.

The write gate consults **approved_policy only** — never the imported hints.
Unknown / unreviewed => fail-closed (treated as side-effecting).

  * ImportedHints   — from MCP ToolAnnotations / OpenAPI. UNTRUSTED.
  * ApprovedPolicy  — human-frozen, authoritative. The gate reads this.
  * RuntimeLimits   — timeout / max rows / retry.
  * Authorization   — required scopes / data classification.
  * WriteSemantics  — destructive / idempotent / requires_confirmation.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class EffectClass(str, Enum):
    # v1alpha1 is binary; richer classes (create/update/delete/external_send)
    # arrive in phase 2 without breaking this enum (additive).
    read_only = "read_only"
    has_side_effect = "has_side_effect"


class ImportedHints(BaseModel):
    """Untrusted hints imported from MCP ToolAnnotations / OpenAPI.
    NEVER sufficient to authorize a write on their own."""

    read_only_hint: bool | None = None
    destructive_hint: bool | None = None
    idempotent_hint: bool | None = None
    open_world_hint: bool | None = None
    output_schema: dict | None = None


class ApprovedPolicy(BaseModel):
    """Authoritative, human-frozen effect policy — the only thing the write gate
    trusts. Default is fail-closed: ``has_side_effect`` and ``reviewed=False``."""

    effect_class: EffectClass = EffectClass.has_side_effect
    reviewed: bool = False
    reviewer: str | None = None
    frozen_at: str | None = None


class RuntimeLimits(BaseModel):
    timeout_ms: int = 10_000
    max_result_rows: int = 100
    retry_policy: str = "safe_only"


class Authorization(BaseModel):
    required_scopes: list[str] = Field(default_factory=list)
    data_classification: str = "internal"


class WriteSemantics(BaseModel):
    destructive: bool = False
    idempotent: bool = True
    requires_confirmation: bool = True


class ToolEffect(BaseModel):
    imported_hints: ImportedHints = Field(default_factory=ImportedHints)
    approved_policy: ApprovedPolicy = Field(default_factory=ApprovedPolicy)
    runtime_limits: RuntimeLimits = Field(default_factory=RuntimeLimits)
    authorization: Authorization = Field(default_factory=Authorization)
    write_semantics: WriteSemantics = Field(default_factory=WriteSemantics)

    @property
    def is_read_only(self) -> bool:
        """True only when a human has reviewed and frozen the policy as read-only.
        Unreviewed or unknown => False (fail-closed)."""
        return (
            self.approved_policy.reviewed
            and self.approved_policy.effect_class is EffectClass.read_only
        )
