#!/usr/bin/env python3
"""mock_acp_backend.py

Deterministic fake ACP stdio backend for testing.

Reads newline-delimited JSON-RPC 2.0 requests from stdin and writes
JSON-RPC 2.0 responses to stdout.  Designed to be launched as a
subprocess by tests via ACPLauncher or directly via subprocess.Popen.

Supported methods:
  initialize  -> returns server capabilities + session id
  chat/complete -> returns a hard-coded assistant message

Unknown methods return a JSON-RPC error response so error-mapping
tests can exercise that path without a real backend.

Usage (subprocess launched by tests):
    cmd = ["python", "tests/helpers/mock_acp_backend.py"]
"""

import json
import sys


def make_response(req_id: int, result: dict) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result})


def make_error(req_id, code: int, message: str) -> str:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
    )


def handle(line: str) -> str:
    try:
        req = json.loads(line.strip())
    except json.JSONDecodeError:
        return make_error(None, -32700, "Parse error")

    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})

    if method == "initialize":
        return make_response(
            req_id,
            {
                "serverInfo": {"name": "mock-acp-backend", "version": "0.0.1"},
                "capabilities": {"chat": True, "tools": False},
                "sessionId": "mock-session-001",
            },
        )

    if method == "chat/complete":
        messages = params.get("messages", [])
        last_user = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "user"),
            "hello",
        )
        return make_response(
            req_id,
            {
                "id": "chatcmpl-mock-001",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": f"mock reply to: {last_user}",
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 8, "total_tokens": 13},
            },
        )

    # Unknown method
    return make_error(req_id, -32601, f"Method not found: {method}")


def main():
    for line in sys.stdin:
        if not line.strip():
            continue
        resp = handle(line)
        sys.stdout.write(resp + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
