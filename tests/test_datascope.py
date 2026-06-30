"""M1: per-row DataScope is the differentiator — non-admins never see others' rows.
This is the over-scope ("越权") gate in miniature (pure, no langchain)."""
from __future__ import annotations

from agent_core.schemas.identity import Principal
from plugins.demo.data import TICKETS
from plugins.demo.providers import DemoDataScope

scope = DemoDataScope()


def _p(subject: str, *roles: str) -> Principal:
    return Principal(issuer="test", subject=subject, roles=list(roles))


def test_member_sees_only_own_rows():
    rows = scope.scope_query(TICKETS, _p("alice", "member"))
    assert {r["id"] for r in rows} == {1, 2}            # alice owns 1, 2
    assert all(r["owner"] == "alice" for r in rows)


def test_other_member_sees_disjoint_rows():
    rows = scope.scope_query(TICKETS, _p("bob", "member"))
    assert {r["id"] for r in rows} == {3, 4}


def test_admin_sees_all_rows():
    rows = scope.scope_query(TICKETS, _p("root", "admin"))
    assert {r["id"] for r in rows} == {1, 2, 3, 4}


def test_post_filter_is_defense_in_depth():
    # Even if a leaked row reaches post_filter, it is dropped for a non-owner.
    leaked = TICKETS  # pretend the source returned everything
    assert {r["id"] for r in scope.post_filter(leaked, _p("alice", "member"))} == {1, 2}
