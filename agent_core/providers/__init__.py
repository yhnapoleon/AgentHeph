"""Provider interfaces an app plugin implements."""
from agent_core.providers.base import (
    AuthAdapter,
    DataScopeAdapter,
    KnowledgeProvider,
    ToolProvider,
)

__all__ = ["ToolProvider", "KnowledgeProvider", "AuthAdapter", "DataScopeAdapter"]
