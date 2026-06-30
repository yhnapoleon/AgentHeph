"""M0: manifest schema validates a minimal guide manifest, reserves phase-2 fields,
and the effect model is fail-closed."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_core.schemas.effect import ApprovedPolicy, EffectClass, ToolEffect
from agent_core.schemas.manifest import (
    MANIFEST_API_VERSION,
    Capability,
    ChatbotManifest,
)


def _minimal_guide_manifest() -> dict:
    return {
        "metadata": {"id": "demo-guide", "display_name": "Demo Guide"},
        "capabilities": ["guide"],
        "model": {"endpoint_ref": "gateway", "default": "gpt-oss-120b"},
        "tools": {"provider": "demo.ToolProvider"},
        "rbac": {"principal_adapter": "demo.AuthAdapter"},
    }


def test_minimal_guide_manifest_validates():
    m = ChatbotManifest.model_validate(_minimal_guide_manifest())
    assert m.api_version == MANIFEST_API_VERSION
    assert m.metadata.id == "demo-guide"
    assert m.capabilities == [Capability.guide]
    assert m.knowledge.discovery == "enum"
    assert m.tools.governance.per_tool_call_limit == 25


def test_phase2_fields_reserved_default_none():
    m = ChatbotManifest.model_validate(_minimal_guide_manifest())
    assert m.tenant_id is None
    assert m.credential_context is None
    assert m.sync is None
    assert m.tools.sources == []


def test_invalid_capability_rejected():
    bad = _minimal_guide_manifest()
    bad["capabilities"] = ["delete_everything"]
    with pytest.raises(ValidationError):
        ChatbotManifest.model_validate(bad)


def test_effect_is_fail_closed_by_default():
    # Unreviewed / default policy must NOT be treated as read-only.
    assert ToolEffect().is_read_only is False
    # Only a human-reviewed read_only policy is read-only.
    eff = ToolEffect(approved_policy=ApprovedPolicy(effect_class=EffectClass.read_only, reviewed=True))
    assert eff.is_read_only is True
    # Read-only class but unreviewed -> still fail-closed.
    eff2 = ToolEffect(approved_policy=ApprovedPolicy(effect_class=EffectClass.read_only, reviewed=False))
    assert eff2.is_read_only is False
