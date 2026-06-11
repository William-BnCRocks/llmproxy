"""tests/test_acp_e2e.py

End-to-end contract tests for the ACP stdio client using a deterministic
mock backend.  No real Cursor/Claude binary or network access required.

Coverage:
  - happy-path chat roundtrip (initialize + chat/complete)
  - error-response mapping (unknown method → ACPBackendError with code)
  - subprocess crash / EOF handling
  - subprocess timeout handling
  - clean connect → disconnect lifecycle

The mock backend lives in tests/helpers/mock_acp_backend.py.
"""

import json
import sys
import textwrap
import time
from pathlib import Path

import pytest

from acp.client import ACPBackendError, ACPClient
from acp.config import ACPConfig

# Path to the helper script (absolute so tests can be run from any cwd)
HELPERS_DIR = Path(__file__).parent / "helpers"
MOCK_BACKEND = str(HELPERS_DIR / "mock_acp_backend.py")
PYTHON = sys.executable


# ── fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_config() -> ACPConfig:
    """Config that points to our deterministic mock backend."""
    return ACPConfig(
        backend="cursor",
        command=[PYTHON, MOCK_BACKEND],
        args=[],
    )


@pytest.fixture
def connected_client(mock_config: ACPConfig) -> ACPClient:
    """Start the mock backend and perform the handshake; tear down after test."""
    client = ACPClient(mock_config)
    client.connect()
    yield client
    client.disconnect()


# ── happy-path roundtrip ────────────────────────────────────────────────────


def test_connect_handshake_succeeds(mock_config: ACPConfig) -> None:
    """connect() completes without raising when the backend answers initialize."""
    client = ACPClient(mock_config)
    client.connect()
    assert client.is_connected()
    client.disconnect()


def test_chat_roundtrip_returns_assistant_message(connected_client: ACPClient) -> None:
    """chat() returns an OpenAI-compatible dict with an assistant choice."""
    resp = connected_client.chat(
        messages=[{"role": "user", "content": "hello"}],
        model="cursor-default",
    )
    assert resp["object"] == "chat.completion"
    choices = resp["choices"]
    assert len(choices) == 1
    msg = choices[0]["message"]
    assert msg["role"] == "assistant"
    assert "hello" in msg["content"]


def test_chat_roundtrip_usage_present(connected_client: ACPClient) -> None:
    """chat() response includes token usage fields."""
    resp = connected_client.chat(
        messages=[{"role": "user", "content": "count my tokens"}],
        model="cursor-default",
    )
    assert "usage" in resp
    assert resp["usage"]["total_tokens"] > 0


def test_multiple_turns(connected_client: ACPClient) -> None:
    """Sending two sequential messages over the same connection works."""
    r1 = connected_client.chat(
        messages=[{"role": "user", "content": "first"}], model="m"
    )
    r2 = connected_client.chat(
        messages=[{"role": "user", "content": "second"}], model="m"
    )
    assert r1["choices"][0]["message"]["content"] != ""
    assert r2["choices"][0]["message"]["content"] != ""


# ── error mapping ────────────────────────────────────────────────────────────


def test_unknown_method_raises_acp_backend_error(connected_client: ACPClient) -> None:
    """A JSON-RPC error response from the backend raises ACPBackendError."""
    with pytest.raises(ACPBackendError, match="Method not found"):
        connected_client._send_request("unknown/method", {})


def test_chat_error_from_backend_raises(mock_config: ACPConfig) -> None:
    """If the backend returns a JSON-RPC error for chat/complete, chat() raises."""
    # Build a backend that always errors on chat/complete
    error_script = HELPERS_DIR / "mock_acp_error_backend.py"
    error_script.write_text(
        textwrap.dedent(
            """\
            import json, sys
            for line in sys.stdin:
                if not line.strip():
                    continue
                req = json.loads(line.strip())
                rid = req.get("id")
                method = req.get("method", "")
                if method == "initialize":
                    resp = {"jsonrpc":"2.0","id":rid,"result":{"serverInfo":{},"capabilities":{}}}
                else:
                    resp = {"jsonrpc":"2.0","id":rid,"error":{"code":-32000,"message":"backend exploded"}}
                sys.stdout.write(json.dumps(resp) + "\\n")
                sys.stdout.flush()
            """
        )
    )
    cfg = ACPConfig(backend="cursor", command=[PYTHON, str(error_script)], args=[])
    client = ACPClient(cfg)
    client.connect()
    with pytest.raises(ACPBackendError, match="backend exploded"):
        client.chat(messages=[{"role": "user", "content": "hi"}], model="m")
    client.disconnect()


# ── crash / EOF handling ─────────────────────────────────────────────────────


def test_chat_after_backend_crash_raises(mock_config: ACPConfig) -> None:
    """chat() raises ACPBackendError when the backend has already crashed."""
    client = ACPClient(mock_config)
    client.connect()
    assert client.is_connected()
    # Force-kill the backend
    client._launcher.process.kill()
    client._launcher.process.wait()
    with pytest.raises(ACPBackendError):
        client.chat(messages=[{"role": "user", "content": "hi"}], model="m")


def test_chat_subprocess_eof_raises(mock_config: ACPConfig) -> None:
    """chat() raises ACPBackendError when the backend closes stdout (EOF)."""
    # Use a backend that answers initialize then exits immediately
    eof_script = HELPERS_DIR / "mock_acp_eof_backend.py"
    eof_script.write_text(
        textwrap.dedent(
            """\
            import json, sys
            line = sys.stdin.readline()
            req = json.loads(line.strip())
            resp = {"jsonrpc":"2.0","id":req["id"],"result":{"serverInfo":{},"capabilities":{}}}
            sys.stdout.write(json.dumps(resp) + "\\n")
            sys.stdout.flush()
            # exit immediately — next read will hit EOF
            sys.exit(0)
            """
        )
    )
    cfg = ACPConfig(backend="cursor", command=[PYTHON, str(eof_script)], args=[])
    client = ACPClient(cfg)
    client.connect()  # handshake succeeds
    with pytest.raises(ACPBackendError):
        client.chat(messages=[{"role": "user", "content": "hi"}], model="m")


# ── timeout handling ─────────────────────────────────────────────────────────


def test_chat_timeout_raises(mock_config: ACPConfig) -> None:
    """chat() raises ACPBackendError when the backend never responds (timeout)."""
    # Build a backend that answers initialize but hangs on chat/complete
    hang_script = HELPERS_DIR / "mock_acp_hang_backend.py"
    hang_script.write_text(
        textwrap.dedent(
            """\
            import json, sys, time
            for line in sys.stdin:
                if not line.strip():
                    continue
                req = json.loads(line.strip())
                rid = req.get("id")
                method = req.get("method", "")
                if method == "initialize":
                    resp = {"jsonrpc":"2.0","id":rid,"result":{"serverInfo":{},"capabilities":{}}}
                    sys.stdout.write(json.dumps(resp) + "\\n")
                    sys.stdout.flush()
                else:
                    # simulate hang — never respond
                    time.sleep(60)
            """
        )
    )
    cfg = ACPConfig(backend="cursor", command=[PYTHON, str(hang_script)], args=[])
    client = ACPClient(cfg)
    client.connect()
    t0 = time.monotonic()
    with pytest.raises(ACPBackendError, match="[Tt]imeout|timed out"):
        client.chat(
            messages=[{"role": "user", "content": "hang"}],
            model="m",
            timeout=1.0,  # 1 second budget
        )
    elapsed = time.monotonic() - t0
    assert elapsed < 5, f"timeout took {elapsed:.1f}s (expected ~1s)"
    client.disconnect()


# ── clean lifecycle ──────────────────────────────────────────────────────────


def test_disconnect_idempotent(connected_client: ACPClient) -> None:
    """disconnect() can be called multiple times without raising."""
    connected_client.disconnect()
    connected_client.disconnect()  # second call must not raise


def test_is_connected_false_after_disconnect(mock_config: ACPConfig) -> None:
    """is_connected() returns False after disconnect."""
    client = ACPClient(mock_config)
    client.connect()
    assert client.is_connected()
    client.disconnect()
    assert not client.is_connected()
