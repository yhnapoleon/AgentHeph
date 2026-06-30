"""M1: tool governance — exact dedup + runaway cap (pure, no langchain)."""
from __future__ import annotations

from agent_core.runtime.governance import ToolGovernor


def test_exact_dedup_returns_cached_and_calls_once():
    calls = []

    def fn(x):
        calls.append(x)
        return {"x": x}

    g = ToolGovernor()
    assert g.run("t", fn, x=1) == {"x": 1}
    assert g.run("t", fn, x=1) == {"x": 1}   # cached
    assert calls == [1]                       # fn ran only once
    g.run("t", fn, x=2)                        # different args -> runs again
    assert calls == [1, 2]


def test_dedup_is_arg_order_independent():
    g = ToolGovernor()
    seen = []
    g.run("t", lambda **k: seen.append(k) or k, a=1, b=2)
    g.run("t", lambda **k: seen.append(k) or k, b=2, a=1)  # same call, reordered
    assert len(seen) == 1


def test_runaway_cap_returns_error_not_raise():
    g = ToolGovernor(per_tool_call_limit=3, dedup_exact_repeats=False)
    for i in range(3):
        assert "error" not in g.run("t", lambda i=i: {"i": i})
    over = g.run("t", lambda: {"i": 99})
    assert "error" in over and "maximum" in over["error"]


def test_cap_is_per_tool_name():
    g = ToolGovernor(per_tool_call_limit=1, dedup_exact_repeats=False)
    assert "error" not in g.run("a", lambda: {"ok": 1})
    assert "error" not in g.run("b", lambda: {"ok": 1})   # different tool, own budget
    assert "error" in g.run("a", lambda: {"ok": 1})
