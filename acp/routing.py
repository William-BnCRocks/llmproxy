"""acp/routing.py

ACP request routing helpers.

Provides:
- ``is_acp_model(model)`` — True when the model string has an ``acp/`` prefix.
- ``route_acp_request(data, acp_client)`` — translates a litellm-style data
  dict into an ACPClient.chat() call and returns the OpenAI-compatible response.

This module is deliberately thin: it contains *no* business logic beyond prefix
stripping and error translation so that callers (route_llm_request.py, tests)
stay decoupled from the full ACPClient lifecycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from fastapi import HTTPException, status

if TYPE_CHECKING:  # pragma: no cover
    from .client import ACPClient

_ACP_PREFIX = "acp/"


def is_acp_model(model: Any) -> bool:
    """Return True if *model* starts with ``acp/``.

    Safe against None and non-string inputs.
    """
    return isinstance(model, str) and model.startswith(_ACP_PREFIX)


def route_acp_request(
    data: Dict[str, Any],
    acp_client: "ACPClient",
) -> Dict[str, Any]:
    """Route a chat-completions request through the ACP client.

    Strips the ``acp/`` prefix from ``data["model"]`` (if present) so the
    ACP backend sees a plain model name (e.g. ``"cursor-1.5"``), then
    delegates to ``acp_client.chat()``.

    Args:
        data: litellm-style request dict.  Must contain at least ``model``
            and ``messages``.
        acp_client: A connected (or auto-connecting) :class:`~acp.client.ACPClient`.

    Returns:
        OpenAI-compatible ``chat.completion`` dict from the ACP backend.

    Raises:
        ``fastapi.HTTPException`` with status 502 if the ACP backend is
        unreachable or returns a protocol-level error.
    """
    from .client import ACPBackendError

    model_name: str = data.get("model", "")
    if model_name.startswith(_ACP_PREFIX):
        model_name = model_name[len(_ACP_PREFIX):]

    messages = data.get("messages", [])

    # Forward optional chat params (temperature, max_tokens, stream, …)
    _skip = {"model", "messages"}
    extra: Dict[str, Any] = {k: v for k, v in data.items() if k not in _skip}

    try:
        return acp_client.chat(model=model_name, messages=messages, **extra)
    except ACPBackendError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"ACP backend error: {exc}",
        ) from exc
