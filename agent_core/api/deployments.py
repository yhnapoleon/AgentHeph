"""Deployment registry: ``deployment_id`` -> everything needed to run a turn.

The SSE contract says a client picks only a ``deployment_id``; the server resolves it to
an immutable ``manifest_digest`` and the wired providers. This registry is that
resolution. A deployment bundles the manifest with its plugin providers and a model
factory (injected so tests can supply a fake model and so the LLM factory stays out of
the unit-testable core).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from agent_core.manifest import compute_manifest_digest
from agent_core.providers.base import AuthAdapter, ToolProvider
from agent_core.runtime.audit import AuditSink
from agent_core.schemas.manifest import ChatbotManifest


@dataclass
class Deployment:
    deployment_id: str
    manifest: ChatbotManifest
    provider: ToolProvider
    model_factory: Callable[[], object]          # () -> chat model (real or fake)
    auth_adapter: AuthAdapter | None = None
    audit_sink: AuditSink | None = None
    resolved_slots: dict[str, str] = field(default_factory=dict)
    _digest: str = ""

    @property
    def manifest_digest(self) -> str:
        # Immutable for the life of the process; computed once.
        if not self._digest:
            self._digest = compute_manifest_digest(self.manifest)
        return self._digest


class DeploymentRegistry:
    def __init__(self) -> None:
        self._by_id: dict[str, Deployment] = {}

    def register(self, deployment: Deployment) -> None:
        self._by_id[deployment.deployment_id] = deployment

    def get(self, deployment_id: str) -> Deployment | None:
        return self._by_id.get(deployment_id)
