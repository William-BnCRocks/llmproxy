"""Tests for acp/client.py — full JSON-RPC stdio lifecycle."""

import json
import pytest
from unittest.mock import MagicMock, patch

from acp.client import ACPClient, ACPBackendError
from acp.config import ACPConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    return ACPConfig(backend="cursor", command=["cursor", "--acp"], args=[])


def _make_mock_launcher(stdout_lines=None, running=True):
    """Return a mock launcher whose process.stdout.readline feeds *stdout_lines*."""
    mock_launcher = MagicMock()
    mock_proc = MagicMock()
    lines = list(stdout_lines or [])

    def _readline():
        return lines.pop(0) if lines else ""

    mock_proc.stdout.readline.side_effect = _readline
    mock_proc.stdin.write.return_value = None
    mock_proc.stdin.flush.return_value = None
    mock_launcher.is_running.return_value = running
    mock_launcher.process = mock_proc
    return mock_launcher


# ---------------------------------------------------------------------------
# connect() / disconnect() / is_connected()
# ---------------------------------------------------------------------------

def test_connect_raises_when_command_not_found(config):
    """connect() raises ACPBackendError if the backend binary is missing."""
    bad_config = ACPConfig(
        backend="cursor", command=["nonexistent_binary_xyz"], args=[]
    )
    client = ACPClient(bad_config)
    with pytest.raises(ACPBackendError, match="not found"):
        client.connect()


def test_connect_raises_when_process_exits_immediately(config):
    """connect() raises ACPBackendError if the process exits right after start."""
    client = ACPClient(config)
    mock_launcher = MagicMock()
    # is_running: True once (survives start()) then False (exits immediately)
    mock_launcher.is_running.side_effect = [True, False]
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="exited immediately"):
        client.connect()


def test_connect_performs_handshake_on_success(config):
    """connect() sends initialize JSON-RPC and does NOT raise on a valid response."""
    client = ACPClient(config)
    handshake_resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"serverInfo": {"name": "cursor-acp", "version": "0.1"}},
    }) + "\n"
    mock_launcher = _make_mock_launcher(stdout_lines=[handshake_resp])
    mock_launcher.is_running.return_value = True  # running throughout
    client._launcher = mock_launcher
    client.connect()  # must not raise
    # Verify initialize was sent
    written = mock_launcher.process.stdin.write.call_args[0][0]
    msg = json.loads(written)
    assert msg["method"] == "initialize"
    assert msg["jsonrpc"] == "2.0"


def test_disconnect_calls_stop(config):
    """disconnect() delegates to launcher.stop()."""
    client = ACPClient(config)
    mock_launcher = MagicMock()
    client._launcher = mock_launcher
    client.disconnect()
    mock_launcher.stop.assert_called_once()


def test_is_connected_reflects_launcher(config):
    """is_connected() mirrors launcher.is_running()."""
    client = ACPClient(config)
    mock_launcher = MagicMock()
    mock_launcher.is_running.return_value = True
    client._launcher = mock_launcher
    assert client.is_connected() is True
    mock_launcher.is_running.return_value = False
    assert client.is_connected() is False


# ---------------------------------------------------------------------------
# _send_request() — low-level JSON-RPC
# ---------------------------------------------------------------------------

def test_send_request_raises_when_not_running(config):
    """_send_request raises ACPBackendError when backend is not running."""
    client = ACPClient(config)
    with pytest.raises(ACPBackendError, match="not running"):
        client._send_request("test_method", {})


def test_send_request_raises_on_broken_pipe(config):
    """_send_request raises ACPBackendError on BrokenPipeError."""
    client = ACPClient(config)
    mock_launcher = MagicMock()
    mock_proc = MagicMock()
    mock_proc.stdin.write.side_effect = BrokenPipeError("broken")
    mock_launcher.is_running.return_value = True
    mock_launcher.process = mock_proc
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="pipe error"):
        client._send_request("test", {})


def test_send_request_raises_when_stdout_empty(config):
    """_send_request raises ACPBackendError when backend closes stdout (EOF)."""
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=[""])  # EOF
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="closed stdout"):
        client._send_request("test", {})


def test_send_request_raises_on_malformed_json(config):
    """_send_request raises ACPBackendError on non-JSON backend response."""
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=["not-json\n"])
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="malformed JSON"):
        client._send_request("test", {})


def test_send_request_raises_on_jsonrpc_error_response(config):
    """_send_request raises ACPBackendError when response contains JSON-RPC error."""
    error_resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32600, "message": "Invalid Request"},
    }) + "\n"
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=[error_resp])
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="Invalid Request"):
        client._send_request("test", {})


def test_send_request_increments_id(config):
    """Each _send_request call uses a unique, incrementing id."""
    resp1 = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}) + "\n"
    resp2 = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {}}) + "\n"
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=[resp1, resp2])
    client._launcher = mock_launcher

    r1 = client._send_request("m1", {})
    r2 = client._send_request("m2", {})

    calls = mock_launcher.process.stdin.write.call_args_list
    id1 = json.loads(calls[0][0][0])["id"]
    id2 = json.loads(calls[1][0][0])["id"]
    assert id1 != id2
    assert id2 == id1 + 1


# ---------------------------------------------------------------------------
# chat() — high-level completion
# ---------------------------------------------------------------------------

def test_chat_sends_correct_jsonrpc_method(config):
    """chat() sends a JSON-RPC request with method 'chat/completions'."""
    resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "choices": [{"message": {"role": "assistant", "content": "Hello!"}}]
        },
    }) + "\n"
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=[resp])
    client._launcher = mock_launcher

    messages = [{"role": "user", "content": "Hi"}]
    result = client.chat(messages=messages, model="cursor-default")

    written = mock_launcher.process.stdin.write.call_args[0][0]
    msg = json.loads(written)
    assert msg["method"] == "chat/completions"
    assert msg["params"]["messages"] == messages
    assert msg["params"]["model"] == "cursor-default"


def test_chat_returns_assistant_content(config):
    """chat() extracts and returns the assistant reply text."""
    content = "The answer is 42."
    resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "choices": [{"message": {"role": "assistant", "content": content}}]
        },
    }) + "\n"
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=[resp])
    client._launcher = mock_launcher

    result = client.chat(messages=[{"role": "user", "content": "?"}])
    assert result == content


def test_chat_raises_on_backend_not_running(config):
    """chat() raises ACPBackendError when backend is not running."""
    client = ACPClient(config)
    with pytest.raises(ACPBackendError, match="not running"):
        client.chat(messages=[{"role": "user", "content": "hi"}])


def test_chat_raises_on_jsonrpc_error(config):
    """chat() propagates ACPBackendError from JSON-RPC error responses."""
    error_resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "error": {"code": -32603, "message": "Internal error"},
    }) + "\n"
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=[error_resp])
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="Internal error"):
        client.chat(messages=[{"role": "user", "content": "hi"}])


def test_chat_with_extra_params(config):
    """chat() forwards extra keyword args (temperature, max_tokens, etc.) in params."""
    resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}]
        },
    }) + "\n"
    client = ACPClient(config)
    mock_launcher = _make_mock_launcher(stdout_lines=[resp])
    client._launcher = mock_launcher

    client.chat(
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.5,
        max_tokens=100,
    )

    written = mock_launcher.process.stdin.write.call_args[0][0]
    params = json.loads(written)["params"]
    assert params["temperature"] == 0.5
    assert params["max_tokens"] == 100


# ---------------------------------------------------------------------------
# Context manager support
# ---------------------------------------------------------------------------

def test_context_manager_connects_and_disconnects(config):
    """ACPClient used as a context manager calls connect() and disconnect()."""
    client = ACPClient(config)
    handshake_resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"serverInfo": {"name": "cursor-acp", "version": "0.1"}},
    }) + "\n"
    mock_launcher = _make_mock_launcher(stdout_lines=[handshake_resp])
    mock_launcher.is_running.return_value = True
    client._launcher = mock_launcher

    with client:
        pass  # inside the block; disconnect called on exit

    mock_launcher.stop.assert_called_once()


def test_context_manager_disconnects_on_exception(config):
    """ACPClient context manager still calls disconnect() if an exception is raised."""
    client = ACPClient(config)
    handshake_resp = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"serverInfo": {"name": "cursor-acp"}},
    }) + "\n"
    mock_launcher = _make_mock_launcher(stdout_lines=[handshake_resp])
    mock_launcher.is_running.return_value = True
    client._launcher = mock_launcher

    with pytest.raises(ValueError):
        with client:
            raise ValueError("something went wrong")

    mock_launcher.stop.assert_called_once()
