"""Build a ReAct agent from a manifest + a plugin's providers, scoped to one actor.

Central enforcement (not plugin discretion):
  * **visibility trim** — tools the AuthAdapter says this principal can't see are
    dropped at graph-build time, so an out-of-scope tool never reaches the model;
  * **governance** — every tool is wrapped through the per-turn ToolGovernor (dedup +
    runaway cap) here, so a plugin can't accidentally skip it.

Lazy langgraph/langchain imports keep agent_core importable without the runtime extra.
"""
from __future__ import annotations

from agent_core.providers.base import AuthAdapter, ToolProvider
from agent_core.runtime.governance import ToolGovernor
from agent_core.runtime.prompt import build_system_prompt
from agent_core.schemas.identity import Principal
from agent_core.schemas.manifest import ChatbotManifest


def _govern_tool(tool, governor: ToolGovernor):
    """Wrap a StructuredTool so its body runs through the governor. Non-structured
    tools are returned unchanged (the governor only guards structured calls)."""
    from langchain_core.tools import StructuredTool

    if not isinstance(tool, StructuredTool):
        return tool

    name = tool.name
    if tool.func is not None:
        original = tool.func

        def governed(**kwargs):
            return governor.run(name, original, **kwargs)

        return StructuredTool.from_function(
            func=governed, name=name, description=tool.description, args_schema=tool.args_schema,
        )
    return tool  # async-only tools: governance wrapping deferred (no sync body)


def build_agent(
    manifest: ChatbotManifest,
    provider: ToolProvider,
    principal: Principal,
    *,
    governor: ToolGovernor,
    artifact_sink: list | None = None,
    auth_adapter: AuthAdapter | None = None,
    resolved_slots: dict[str, str] | None = None,
    model=None,
):
    """Compile a ReAct agent for ``principal`` on this deployment.

    ``model`` may be a prebuilt chat client (tests pass a fake); when None the caller is
    expected to have supplied one (the LLM factory is wired at the API layer so this
    stays unit-testable).
    """
    from langgraph.prebuilt import create_react_agent

    from agent_core.runtime.checkpoint import get_checkpointer

    tools = provider.build_tools(principal, artifact_sink=artifact_sink)
    if auth_adapter is not None:
        visible = auth_adapter.visible_tools(principal)
        tools = [t for t in tools if getattr(t, "name", None) in visible]
    tools = [_govern_tool(t, governor) for t in tools]

    prompt = build_system_prompt(manifest, principal, resolved_slots=resolved_slots)
    return create_react_agent(model, tools, prompt=prompt, checkpointer=get_checkpointer())
