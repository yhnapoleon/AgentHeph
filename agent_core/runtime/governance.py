"""Per-turn tool governance — the platform's enforced version of BAU's ``_run``.

Two guards, applied to every tool call regardless of which plugin built the tool
(so dedup/runaway semantics can never drift per-plugin, and a plugin can't opt out):

  * **exact dedup** — a repeat call with identical args returns the cached result
    (the prompt's "调用克制" discipline turned into a mechanism);
  * **runaway cap** — a per-turn backstop against a "keep tweaking params" loop.
    BAU evidence: the cap must stay well above legitimate fan-out (drilling into a
    dozen jobs is normal); a 2nd-round regression set it to 6 and broke a valid
    "check every job" task — never go that low. Default 25.

The governor is data-layer agnostic: identity/session injection stays in the
plugin's ToolProvider (it owns its data access). The governor only sees
``(tool_name, kwargs) -> result``.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _dedup_key(name: str, kwargs: dict) -> tuple:
    # repr of sorted items: order-independent and hashable for arbitrary JSON-ish args.
    return (name, repr(sorted(kwargs.items())))


class RunawayLimitError(RuntimeError):
    """Raised internally when a tool exceeds the per-turn call cap; surfaced to the
    model as a structured tool result, not a crash."""


class ToolGovernor:
    """Holds per-turn call state. Build one per turn (it is not thread-safe and is
    intentionally short-lived)."""

    def __init__(self, *, per_tool_call_limit: int = 25, dedup_exact_repeats: bool = True) -> None:
        self.per_tool_call_limit = per_tool_call_limit
        self.dedup_exact_repeats = dedup_exact_repeats
        self._cache: dict[tuple, Any] = {}
        self._counts: dict[str, int] = {}

    def run(self, name: str, fn: Callable[..., Any], **kwargs: Any) -> Any:
        """Invoke ``fn(**kwargs)`` under dedup + runaway guards.

        On the cap being hit, returns a structured error dict (the model reads it and
        is told to answer with what it already has) rather than raising — matching BAU.
        """
        key = _dedup_key(name, kwargs)
        if self.dedup_exact_repeats and key in self._cache:
            return self._cache[key]

        self._counts[name] = self._counts.get(name, 0) + 1
        if self._counts[name] > self.per_tool_call_limit:
            logger.warning("runaway cap hit for tool %s (limit %d)", name, self.per_tool_call_limit)
            return {
                "error": (
                    f"This turn has called '{name}' the maximum number of times "
                    f"({self.per_tool_call_limit}). Answer with the results already "
                    f"gathered, or use a more aggregate tool."
                )
            }

        result = fn(**kwargs)
        if self.dedup_exact_repeats:
            self._cache[key] = result
        return result
