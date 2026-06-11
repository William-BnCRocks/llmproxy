"""litellm.llms.acp — ACP (Agent Communication Protocol) provider for litellm.

This package wires the ACP JSON-RPC stdio client (acp.client.ACPClient) into
litellm's provider dispatch so that requests with ``custom_llm_provider="acp"``
or model names prefixed with ``"acp/"`` are routed to a locally-launched ACP
backend (e.g. Cursor, Claude).

Public surface
--------------
``acp_completion(model, messages, acp_config, **kwargs)``
    Synchronous completion call.  Returns an OpenAI-compatible dict.

``async_acp_completion(model, messages, acp_config, **kwargs)``
    Async wrapper — runs acp_completion in the default thread-pool executor.

See ``litellm/llms/acp/completion.py`` for implementation details.
"""

from litellm.llms.acp.completion import acp_completion, async_acp_completion

__all__ = ["acp_completion", "async_acp_completion"]
