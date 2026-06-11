Read @CLAUDE.md for coding guidelines

# llmproxy Project Patterns (updated via orchestrator task t_b63bd6b7 after MCP is not ACP clarification)

## ACP Integration
- llmproxy implements **ACP client** only (launches and speaks stdio JSON-RPC *to* Cursor/Claude ACP backends).
- MCP is **not** ACP — keep protocols cleanly separated. Reference any existing ACP client connections Hermes supports (or the general ACP protocol specs for IDE/agent backends). Do **not** reference MCP client code.
- `hermes acp` is the server side (Hermes *providing* ACP to IDEs) — llmproxy is client only.
- Structure: acp/ (launcher.py for process management/auto-restart, client.py for JSON-RPC, session.py for mapping, adapters/cursor.py).
- Config-driven auto-detect and launch. Exposes standard OpenAI-compatible API for Hermes.
- All code follows TDD, requesting-code-review before commits/PRs.

## Development Workflow
- All work on dedicated `llmproxy` Kanban board (not default).
- Orchestrator watches board + GitHub PR webhooks (canonical https://webhooks.hermes.bnc.rocks/webhooks/github-pr-kanban).
- On PR review comments (inline or formal), orchestrator creates follow-up Kanban task for original implementer with exact fixes listed. Address *all* comments per github-pr-workflow skill before marking done.
- Use git worktrees (main clean, -dev active). Update this AGENTS.md on every non-trivial change.
- Private repos only. Frequent commits with verification.

**Completed via t_e85dbea3:** Thin hermes-llmproxy plugin created (registration only). ACP backend config parsing/passthrough implemented in plugin. hermes-llmproxy repo now has the minimal provider registration.

See docs/plans/2026-06-10-llmproxy-acp-client.md for full bite-sized task breakdown (writing-plans compliant, TDD, ACP client only, Kanban orchestration). Updated via t_183d463f. Hindsight memory noted: similar to setting `auto_retain: false` in ~/.hermes/hindsight/config.json (opened in Zed, no stored memories, Ollama backend), we maintain clean separation here.

**Completed via t_50268eab (Task 4):** `acp/client.py` is the canonical ACP JSON-RPC stdio client. Public API:

```python
from acp.client import ACPClient, ACPBackendError
from acp.config import ACPConfig

config = ACPConfig(backend="cursor", command=["cursor", "--acp"], args=[])

# Option A: context manager (recommended)
with ACPClient(config) as client:
    reply: str = client.chat(
        messages=[{"role": "user", "content": "Hello!"}],
        model="cursor-default",   # optional
        temperature=0.7,          # any extra kwargs forwarded in JSON-RPC params
    )

# Option B: manual lifecycle
client = ACPClient(config)
client.connect()       # starts process + initialize handshake
reply = client.chat(messages=[...])
client.disconnect()    # graceful shutdown
```

`ACPBackendError` is raised on: command not found, process exits immediately,
broken pipe, malformed JSON response, JSON-RPC error object in response, or
calling chat() while not connected.  Task 5 (routing wire-up) should import
`ACPClient` + `ACPBackendError` from `acp.client` and `ACPConfig` from `acp.config`.