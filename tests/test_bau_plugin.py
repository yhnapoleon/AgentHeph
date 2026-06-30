"""M1.2: the BAU adapter conforms to the provider interfaces. The tool/auth/knowledge
methods need BAU's ``core.*`` runtime (separate repo) so they are skipped here; the M1
behavior-equivalence acceptance runs in the BAU environment, not this CI."""
from __future__ import annotations

import importlib.util

import pytest

from agent_core.providers.base import (
    AuthAdapter,
    DataScopeAdapter,
    KnowledgeProvider,
    ToolProvider,
)
from agent_core.schemas.identity import Principal
from plugins.bau import BauAuth, BauDataScope, BauKnowledge, BauTools

def _bau_available() -> bool:
    # bau_center's agent layer specifically — not just any top-level `core` package.
    try:
        return importlib.util.find_spec("core.agent.tools") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


_BAU_AVAILABLE = _bau_available()


def test_adapters_implement_the_interfaces():
    assert isinstance(BauTools(), ToolProvider)
    assert isinstance(BauDataScope(), DataScopeAdapter)
    assert isinstance(BauAuth(), AuthAdapter)
    assert isinstance(BauKnowledge(), KnowledgeProvider)


def test_bau_datascope_is_source_side_no_op():
    # BAU scopes inside each tool's query; the adapter must not re-fetch/re-filter.
    scope = BauDataScope()
    p = Principal(issuer="bau", subject="alice", roles=["bau_member"])
    rows = [{"id": 1}, {"id": 2}]
    assert scope.scope_query(rows, p) is rows
    assert scope.post_filter(rows, p) == rows


@pytest.mark.skipif(not _BAU_AVAILABLE, reason="bau_center core.* not on path (separate repo)")
def test_bau_tools_build_under_bau_runtime():
    tools = BauTools().build_tools(Principal(issuer="bau", subject="alice", roles=["bau_member"]))
    assert all(hasattr(t, "name") for t in tools)
