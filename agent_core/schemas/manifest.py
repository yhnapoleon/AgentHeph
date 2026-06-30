"""Chatbot manifest (M0 contract, ``agentstudio/v1alpha1``).

A manifest fully declares one chatbot deployment. v1alpha1 is intentionally NOT
frozen — additive fields are fine; rename/remove/semantic-change is breaking and
needs review. Phase-2-only fields are present but reserved (no machinery yet).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

MANIFEST_API_VERSION = "agentstudio/v1alpha1"


class Capability(str, Enum):
    guide = "guide"            # explain features / fields / navigation (UI-first KB)
    data_read = "data_read"    # read-only data queries (phase 2)
    propose_write = "propose_write"  # human-confirmed write proposals (phase 2)


class Metadata(BaseModel):
    id: str
    version: int = 1
    display_name: str
    description: str = ""


class ModelConfig(BaseModel):
    endpoint_ref: str          # reference into secret store, never inline
    default: str
    light: str | None = None
    vision: str | None = None
    api_format: str = "openai"


class ToolGovernance(BaseModel):
    per_tool_call_limit: int = 25
    dedup_exact_repeats: bool = True
    # phase-2 budgets (reserved)
    max_total_calls: int | None = None
    max_graph_steps: int | None = None
    wall_clock_ms: int | None = None
    concurrency: int | None = None


class ToolSource(BaseModel):
    """Reserved (phase 2): where tools are imported from."""

    type: str  # "mcp" | "openapi"
    ref: str | None = None
    auth_ref: str | None = None
    trust_level: str | None = None


class ToolsConfig(BaseModel):
    provider: str
    # M0 binary effect bind: tool_name -> "read_only" | "has_side_effect".
    # Full ToolEffect policy is stored/frozen separately (phase 2).
    effects: dict[str, str] = Field(default_factory=dict)
    governance: ToolGovernance = Field(default_factory=ToolGovernance)
    sources: list[ToolSource] = Field(default_factory=list)  # reserved


class KnowledgePartition(BaseModel):
    area: str  # domain/entity key (UI page is only a source_ref, not the key)
    sources: list[dict] = Field(default_factory=list)


class KnowledgeConfig(BaseModel):
    partitions: list[KnowledgePartition] = Field(default_factory=list)
    discovery: str = "enum"  # "enum" | "retrieval" (eval-driven switch)


class RbacConfig(BaseModel):
    principal_adapter: str
    data_scope_adapter: str | None = None  # required for data_read/edit (per-row)
    visibility: dict[str, list[str]] = Field(default_factory=dict)  # area/tool -> roles


class PromptConfig(BaseModel):
    discipline_profile: str = "strict-internal"
    slots: dict[str, str] = Field(default_factory=dict)


class EvalConfig(BaseModel):
    golden_set_ref: str | None = None
    gates: list[str] = Field(default_factory=list)


class AuditConfig(BaseModel):
    sink: str = "agent_run"
    retention_days: int = 365


class ChatbotManifest(BaseModel):
    api_version: str = Field(default=MANIFEST_API_VERSION, alias="apiVersion")
    kind: str = "ChatbotManifest"
    metadata: Metadata
    capabilities: list[Capability]
    model: ModelConfig
    tools: ToolsConfig
    knowledge: KnowledgeConfig = Field(default_factory=KnowledgeConfig)
    rbac: RbacConfig
    prompt: PromptConfig = Field(default_factory=PromptConfig)
    eval: EvalConfig = Field(default_factory=EvalConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)

    # ---- reserved (phase 2; declared so the schema is forward-compatible) ----
    tenant_id: str | None = None
    credential_context: dict | None = None
    sync: dict | None = None  # spec-diff / UI-diff config

    model_config = {"populate_by_name": True}
