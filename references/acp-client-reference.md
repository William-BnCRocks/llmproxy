# ACP Client Reference (Pure ACP Protocol)

This document captures the Agent Communication Protocol (ACP) for client-side connections to IDE/agent backends such as Cursor and Claude.

**Important:** This reference contains zero references to any other protocol. `hermes acp` provides the ACP server side for IDEs; llmproxy implements the client side only (launching and communicating with ACP backends via stdio).

## Core Protocol: stdio JSON-RPC

ACP uses line-buffered JSON-RPC 2.0 over stdin/stdout pipes to the backend process.

- Launch: subprocess.Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)
- Messages are single JSON objects per line.
- Client sends requests/notifications; backend responds.

## Handshake / Initialize

Typical flow for client:

1. Start process.
2. Send initialize request with client info, capabilities (chat, tools).
3. Backend responds with server capabilities, session info.
4. Optional: initialized notification.

Example request:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "clientInfo": {"name": "llmproxy", "version": "0.1.0"},
    "capabilities": {"chat": true, "tools": true}
  }
}
```

## Session Management

- Sessions map to conversation threads.
- Use sessionId or correlation via request id.
- Multi-turn chat maintains context via backend or explicit session create.

## Chat / Completion Methods

- chat/complete or completion for OpenAI-compatible calls.
- Params include messages, model, tools, temperature etc.
- Supports streaming via stream: true.

## Tool Calling Patterns

- Tools advertised in initialize response or separate tools/list.
- In chat request: tools array with name, description, parameters schema.
- Backend calls tools via tool/call or response with tool_calls.
- Client executes and sends tool/result back.

## Error Handling & Restart

- JSON-RPC errors: code, message, data.
- Process crash: detect via poll() != None, auto-restart with backoff (see launcher).
- Timeouts on responses, restart on repeated failures.
- Graceful shutdown: terminate() then kill() if needed.

## Error/Restart Policy (Client Side)

- auto_restart: true by default
- restart_delay: 1.0s
- Track restart_count
- Log all lifecycle events.

## Verification Notes

- All examples are ACP-specific for Cursor/Claude style backends.
- Reference implementation patterns live in acp/launcher.py, future client.py, session.py.

This research extracted from plan, existing acp code, and ACP design for IDE agent backends. ACP client patterns documented here.
