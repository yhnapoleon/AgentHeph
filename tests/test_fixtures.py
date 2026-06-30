"""M0 contract fixtures (ROADMAP #8): two manifests stress the v1alpha1 schema so it
isn't overfit to BAU before we consider freezing v1. BAU = first real app; Expensly = a
deliberately different second app (OpenAPI-imported tools, delegated-user creds,
multi-tenant, org-hierarchy per-row scope, a write tool). Paper-only — no app is built.
"""
from __future__ import annotations

import pathlib

import pytest
import yaml

from agent_core.manifest import compute_manifest_digest, load_manifest
from agent_core.schemas.manifest import Capability

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "contracts" / "fixtures"
BAU = FIXTURES / "bau" / "manifest.yaml"
EXPENSLY = FIXTURES / "expensly" / "manifest.yaml"
EXPENSLY_OPENAPI = FIXTURES / "expensly" / "openapi.yaml"


@pytest.mark.parametrize("path", [BAU, EXPENSLY], ids=["bau", "expensly"])
def test_fixture_manifest_validates(path):
    m = load_manifest(path)
    assert m.metadata.id
    assert m.rbac.principal_adapter
    assert m.tools.effects, "fixtures declare explicit, human-frozen effects"


def test_bau_is_the_first_party_native_end_of_the_schema():
    m = load_manifest(BAU)
    assert m.tools.sources == []          # native tools, nothing imported
    assert m.credential_context is None   # service-account default
    assert m.tenant_id is None            # single-tenant
    assert m.rbac.data_scope_adapter      # per-row still required


def test_expensly_exercises_reserved_phase2_shape():
    """The whole point of the second fixture: it must touch the reserved fields, so we
    know the schema carries a non-BAU app without a breaking change."""
    m = load_manifest(EXPENSLY)
    assert any(s.type == "openapi" for s in m.tools.sources)            # imported tools
    assert m.credential_context and m.credential_context["mode"] == "delegated_user"
    assert m.tenant_id == "acme"                                        # multi-tenant
    assert m.sync                                                       # spec-diff config
    assert m.tools.effects["approve_expense_report"] == "has_side_effect"   # write tool
    assert m.rbac.data_scope_adapter                                   # per-row scope
    assert "employee" not in m.rbac.visibility["approvals"]            # restricted write
    assert set(m.capabilities) == {
        Capability.guide,
        Capability.data_read,
        Capability.propose_write,
    }


def test_expensly_openapi_parses_and_every_op_is_governed():
    """Desensitized OpenAPI parses, and every imported operation has an effect entry
    (no operation silently ungoverned)."""
    spec = yaml.safe_load(EXPENSLY_OPENAPI.read_text(encoding="utf-8"))
    op_ids = {
        op["operationId"]
        for path_item in spec["paths"].values()
        for op in path_item.values()
        if isinstance(op, dict) and "operationId" in op
    }
    effects = load_manifest(EXPENSLY).tools.effects
    assert op_ids, "fixture OpenAPI declares operations"
    assert op_ids <= set(effects), f"ungoverned operations: {op_ids - set(effects)}"


def test_manifest_digest_is_stable_and_distinct():
    bau_digest = compute_manifest_digest(load_manifest(BAU))
    assert bau_digest.startswith("sha256:")
    # Reloading the same file yields the same immutable digest.
    assert compute_manifest_digest(load_manifest(BAU)) == bau_digest
    # Different manifests -> different digests.
    assert compute_manifest_digest(load_manifest(EXPENSLY)) != bau_digest
