"""Chat-model factory — generalized from BAU's ``llm.py``.

Manifest-driven: the model tier names live in ``manifest.model`` and the endpoint +
credentials are resolved from a secret store via ``endpoint_ref`` (never inline). Lazy
and guarded — importing agent_core never talks to a gateway, and the package works
when langchain-openai isn't installed (the error only fires when a model is requested).

OpenAI-compatible gateways are covered via ``base_url`` override (the bank runs an
internal OpenAI-compatible coordinator behind its own CA — the resolver supplies
``verify``).
"""
from __future__ import annotations

import os
import re
from typing import Any, Callable

from agent_core.schemas.manifest import ModelConfig

try:
    from langchain_openai import ChatOpenAI  # type: ignore

    _LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only where the extra is absent
    ChatOpenAI = None  # type: ignore[assignment]
    _LANGCHAIN_AVAILABLE = False


class AgentDependencyError(Exception):
    """The runtime extra isn't installed (``pip install .[runtime]``)."""


class LlmNotConfiguredError(Exception):
    """The endpoint_ref did not resolve to an endpoint + token."""


# A secret resolver maps an ``endpoint_ref`` to connection settings. Returning at least
# ``{"endpoint": ..., "token": ...}``; optional ``verify`` (bool | CA path) and
# ``timeout``. Injected so tests and deployments control credential sourcing.
SecretResolver = Callable[[str], dict]


def env_secret_resolver(endpoint_ref: str) -> dict:
    """Default resolver: read ``<REF>_ENDPOINT`` / ``<REF>_TOKEN`` from the environment
    (ref upper-cased, non-alphanumerics -> ``_``). ``bank-gateway`` -> ``BANK_GATEWAY_*``."""
    prefix = re.sub(r"[^0-9A-Za-z]+", "_", endpoint_ref).upper()
    return {
        "endpoint": os.environ.get(f"{prefix}_ENDPOINT", ""),
        "token": os.environ.get(f"{prefix}_TOKEN", ""),
        "verify": os.environ.get(f"{prefix}_CA_BUNDLE") or True,
    }


def get_chat_model(
    model: ModelConfig,
    *,
    tier: str = "default",
    secret_resolver: SecretResolver = env_secret_resolver,
    **overrides: Any,
):
    """Build a chat client for the configured gateway.

    ``tier``: ``default`` -> ``model.default``; ``light`` -> ``model.light`` (falls back
    to default); ``vision`` -> ``model.vision``. An explicit ``model=`` override wins.
    """
    name = {
        "light": model.light or model.default,
        "vision": model.vision or model.default,
    }.get(tier, model.default)
    name = overrides.pop("model", None) or name

    conn = secret_resolver(model.endpoint_ref)
    endpoint, token = conn.get("endpoint", ""), conn.get("token", "")
    if not endpoint or not token:
        raise LlmNotConfiguredError(
            f"endpoint_ref {model.endpoint_ref!r} did not resolve to endpoint + token"
        )
    if not _LANGCHAIN_AVAILABLE:
        raise AgentDependencyError(
            "langchain-openai is not installed; install the runtime extra: pip install .[runtime]"
        )

    # ChatOpenAI appends /chat/completions, so base_url must end with /v1.
    if not endpoint.rstrip("/").endswith("/v1"):
        endpoint = endpoint.rstrip("/") + "/v1"

    import httpx

    verify = conn.get("verify", True)
    timeout = conn.get("timeout", 60)
    kwargs: dict[str, Any] = {
        "base_url": endpoint,
        "api_key": token,
        "model": name,
        "timeout": timeout,
        "http_client": httpx.Client(verify=verify, timeout=timeout),
        "http_async_client": httpx.AsyncClient(verify=verify, timeout=timeout),
    }
    kwargs.update(overrides)
    return ChatOpenAI(**kwargs)
