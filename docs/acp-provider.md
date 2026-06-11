# ACP Provider — Configuration and Usage

llmproxy includes a built-in ACP (Agent Communication Protocol) provider that
launches an ACP-compatible backend process (e.g. Cursor, Claude) via stdio
JSON-RPC and exposes it as a standard OpenAI-compatible `/v1/chat/completions`
endpoint.

## Architecture

```
Hermes (provider: llmproxy)
    ↓  OpenAI-compatible HTTP
llmproxy gateway (:8766/v1)
    ↓  litellm dispatch  (custom_llm_provider=acp)
litellm/llms/acp/completion.py  →  ACPClient
    ↓  JSON-RPC over stdio
ACP backend process (Cursor, Claude, …)
```

The llmproxy repo owns all ACP client logic.  The `hermes-llmproxy` plugin
only provides provider registration (name, base_url, api_key env var).

## Proxy config.yaml

Add an entry to `model_list` for each ACP backend:

```yaml
model_list:
  - model_name: acp-cursor          # name Hermes uses in requests
    litellm_params:
      model: acp/cursor-default     # "acp/" prefix triggers ACP dispatch
      custom_llm_provider: acp
      acp_config:
        backend: cursor
        command:
          - cursor
          - --acp
        args: []
        env:
          CURSOR_API_KEY: sk-...    # optional; backend-specific
        auto_restart: true
        restart_delay: 1.0

  - model_name: acp-claude
    litellm_params:
      model: acp/claude-3-5-sonnet
      custom_llm_provider: acp
      acp_config:
        backend: claude
        command:
          - claude
          - --acp
        args: []
```

## Provider Detection

litellm detects an ACP request in two ways (checked in order):

1. `custom_llm_provider="acp"` set explicitly in `litellm_params`.
2. Model name starts with `"acp/"` — e.g. `"acp/cursor-default"`.

The `"acp/"` prefix is stripped before forwarding to the backend.

## Hermes Provider Registration

The `hermes-llmproxy` plugin (repo: `hermes-llmproxy`) already registers:

```python
ProviderProfile(
    name="llmproxy",
    aliases=("llm-proxy", "acp-proxy"),
    api_mode="chat_completions",
    env_vars=("LLMPROXY_API_KEY",),
    base_url="http://127.0.0.1:8766/v1",
    auth_type="api_key",
)
```

Hermes config (`~/.hermes/config.yaml` or profile `.env`):

```yaml
providers:
  llmproxy:
    base_url: http://127.0.0.1:8766/v1
    api_key: ${LLMPROXY_API_KEY}
```

Then in Hermes:

```bash
hermes --provider llmproxy --model acp-cursor "Hello, Cursor!"
```

## Code Layout

| Path | Purpose |
|------|---------|
| `acp/config.py` | `ACPConfig` Pydantic model |
| `acp/launcher.py` | `ACPLauncher` — subprocess lifecycle |
| `acp/client.py` | `ACPClient` — JSON-RPC stdio client |
| `acp/routing.py` | `is_acp_model()`, `route_acp_request()` |
| `litellm/llms/acp/__init__.py` | Package re-exports |
| `litellm/llms/acp/completion.py` | `acp_completion()` — litellm handler |
| `litellm/main.py` | `custom_llm_provider == "acp"` dispatch branch |
| `litellm/types/utils.py` | `LlmProviders.ACP = "acp"` enum entry |

## JSON-RPC Wire Protocol

All communication uses newline-delimited JSON over the backend's stdin/stdout:

```
→ {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"clientInfo": {"name": "llmproxy", "version": "0.1.0"}}}
← {"jsonrpc": "2.0", "id": 1, "result": {...}}

→ {"jsonrpc": "2.0", "id": 2, "method": "chat/complete", "params": {"model": "cursor-default", "messages": [...]}}
← {"jsonrpc": "2.0", "id": 2, "result": {"id": "...", "object": "chat.completion", "choices": [...], ...}}
```

## Error Handling

| Condition | Behaviour |
|-----------|-----------|
| Backend command not found | `ACPBackendError` → litellm `APIConnectionError` |
| Backend exits immediately | `ACPBackendError` → litellm `APIConnectionError` |
| JSON-RPC error in response | `ACPBackendError` → litellm `APIConnectionError` |
| Backend stdout EOF | `ACPBackendError` → litellm `APIConnectionError` |
| Timeout | `ACPBackendError` → litellm `APIConnectionError` |
| Route called via HTTP | `HTTPException(502)` from `route_acp_request()` |

## Testing

```bash
# Unit + integration (no real ACP process needed)
pytest tests/test_acp_client.py tests/test_acp_config.py \
       tests/test_acp_launcher.py tests/test_acp_route.py \
       tests/test_acp_litellm_integration.py -q

# E2E (uses mock stdio backends in tests/helpers/)
pytest tests/test_acp_e2e.py -q

# All ACP tests
pytest tests/test_acp*.py -q
```
