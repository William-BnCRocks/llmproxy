"""litellm/llms/acp/completion.py

ACP completion handler.

Bridges litellm's provider-dispatch layer to the ACP JSON-RPC stdio client
(``acp.client.ACPClient``).  This module is intentionally thin — all JSON-RPC
protocol logic lives in ``acp/client.py``; all model-name translation lives in
``acp/routing.py``.

Usage inside litellm (added to litellm/main.py dispatch):

    elif custom_llm_provider == "acp":
        response = _acp_completion(
            model=model,
            messages=messages,
            acp_config=litellm_params.get("acp_config") or kwargs.get("acp_config"),
            **optional_params,
        )

The caller is responsible for converting the returned dict to a
``litellm.ModelResponse`` using ``litellm.ModelResponse(**response)``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

# Import from the top-level acp package (repo root, not litellm internals).
from acp.client import ACPClient, ACPBackendError
from acp.config import ACPConfig


def acp_completion(
    model: str,
    messages: List[Dict[str, Any]],
    acp_config: Optional[ACPConfig],
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute a chat completion request via the ACP backend.

    Opens an ``ACPClient`` context (which starts the backend process and
    performs the JSON-RPC initialize handshake), issues the
    ``chat/complete`` request, and returns the raw OpenAI-compatible response
    dict from the backend.

    Args:
        model: Model identifier forwarded to the ACP backend (any ``acp/``
            prefix should already be stripped by the caller).
        messages: List of ``{"role": ..., "content": ...}`` chat messages.
        acp_config: ``ACPConfig`` instance describing the backend command.
            **Required** — raises ``ValueError`` when ``None``.
        timeout: Optional per-call timeout in seconds.
        **kwargs: Extra parameters forwarded to ``ACPClient.chat()`` (e.g.
            ``temperature``, ``max_tokens``).

    Returns:
        OpenAI-compatible ``chat.completion`` dict.

    Raises:
        ValueError: if ``acp_config`` is ``None``.
        ACPBackendError: if the backend fails to start, the pipe breaks, or
            the backend returns a protocol-level error.
    """
    if acp_config is None:
        raise ValueError(
            "acp_config is required for the ACP provider.  "
            "Pass an ACPConfig instance via litellm_params or as a keyword arg."
        )

    # Strip the "acp/" prefix if the caller hasn't done it yet.
    bare_model = model.removeprefix("acp/") if model else model

    with ACPClient(acp_config) as client:
        return client.chat(
            model=bare_model,
            messages=messages,
            timeout=timeout,
            **kwargs,
        )


async def async_acp_completion(
    model: str,
    messages: List[Dict[str, Any]],
    acp_config: Optional[ACPConfig],
    timeout: Optional[float] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Async wrapper for :func:`acp_completion`.

    Runs the synchronous ACP call in the default thread-pool executor so it
    doesn't block the event loop.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: acp_completion(
            model=model,
            messages=messages,
            acp_config=acp_config,
            timeout=timeout,
            **kwargs,
        ),
    )
