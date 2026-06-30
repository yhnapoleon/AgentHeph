"""Test doubles. Not collected by pytest (no ``test_`` prefix)."""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


class FakeToolModel(BaseChatModel):
    """A chat model that replays a scripted list of AIMessages. ``bind_tools`` is a
    no-op (tools execute via the agent's ToolNode, not the model), so we can drive
    create_react_agent deterministically without a gateway."""

    responses: list = []
    _i: int = PrivateAttr(default=0)

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001
        msg = self.responses[self._i]
        self._i += 1
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @property
    def _llm_type(self) -> str:
        return "fake-tool-model"


def tool_call_msg(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


def final_msg(text: str) -> AIMessage:
    return AIMessage(content=text)
