"""Tests for ACP routing (Task 5): chat() on ACPClient + route_acp_request helper.

TDD: tests written BEFORE implementation. Run to verify RED, then implement.
"""

import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from acp.client import ACPClient, ACPBackendError
from acp.config import ACPConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    return ACPConfig(backend="cursor", command=["cursor", "--acp"], args=[])


@pytest.fixture
def connected_client(config):
    """Return an ACPClient whose launcher is mocked as running."""
    client = ACPClient(config)
    mock_launcher = MagicMock()
    mock_launcher.is_running.return_value = True
    mock_proc = MagicMock()
    client._launcher = mock_launcher
    client._launcher.process = mock_proc
    return client


# ---------------------------------------------------------------------------
# ACPClient.chat() — request serialisation / response parsing
# ---------------------------------------------------------------------------

class TestACPClientChat:
    def test_chat_sends_correct_json_rpc_method(self, connected_client):
        """chat() sends a JSON-RPC request with method 'chat/complete'."""
        mock_proc = connected_client._launcher.process
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "id": "acp-1",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
                "model": "cursor",
            },
        })

        messages = [{"role": "user", "content": "Hello"}]
        result = connected_client.chat(model="cursor", messages=messages)

        written = mock_proc.stdin.write.call_args[0][0]
        payload = json.loads(written.strip())
        assert payload["method"] == "chat/complete"
        assert payload["jsonrpc"] == "2.0"
        assert "id" in payload

    def test_chat_passes_model_and_messages_in_params(self, connected_client):
        """chat() passes model and messages in the JSON-RPC params."""
        mock_proc = connected_client._launcher.process
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "id": "acp-2",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
                "model": "cursor",
            },
        })
        messages = [{"role": "user", "content": "test"}]
        connected_client.chat(model="my-model", messages=messages)

        written = mock_proc.stdin.write.call_args[0][0]
        payload = json.loads(written.strip())
        assert payload["params"]["model"] == "my-model"
        assert payload["params"]["messages"] == messages

    def test_chat_returns_openai_compatible_dict(self, connected_client):
        """chat() returns a dict that looks like an OpenAI ChatCompletion response."""
        expected_result = {
            "id": "acp-3",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "World"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
            "model": "cursor",
        }
        mock_proc = connected_client._launcher.process
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": expected_result,
        })

        result = connected_client.chat(model="cursor", messages=[{"role": "user", "content": "Hi"}])
        assert result == expected_result

    def test_chat_raises_on_jsonrpc_error_response(self, connected_client):
        """chat() raises ACPBackendError when the backend returns a JSON-RPC error."""
        mock_proc = connected_client._launcher.process
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32603, "message": "Internal ACP error"},
        })

        with pytest.raises(ACPBackendError):
            connected_client.chat(model="cursor", messages=[{"role": "user", "content": "hi"}])

    def test_chat_raises_when_not_connected(self, config):
        """chat() raises ACPBackendError when backend is not running."""
        client = ACPClient(config)
        # No mock: _launcher.is_running() returns False (default)
        with pytest.raises(ACPBackendError, match="not running"):
            client.chat(model="cursor", messages=[{"role": "user", "content": "hi"}])

    def test_chat_passes_extra_params(self, connected_client):
        """chat() forwards extra kwargs (temperature, max_tokens) in params."""
        mock_proc = connected_client._launcher.process
        mock_proc.stdout.readline.return_value = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "id": "acp-4",
                "object": "chat.completion",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                "model": "cursor",
            },
        })
        connected_client.chat(
            model="cursor",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=100,
        )
        written = mock_proc.stdin.write.call_args[0][0]
        payload = json.loads(written.strip())
        assert payload["params"]["temperature"] == 0.7
        assert payload["params"]["max_tokens"] == 100


# ---------------------------------------------------------------------------
# acp.routing — route_acp_request helper
# ---------------------------------------------------------------------------

class TestRouteACPRequest:
    def test_route_acp_request_calls_chat(self):
        """route_acp_request calls ACPClient.chat with correct args."""
        from acp.routing import route_acp_request

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "id": "acp-5",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            "model": "cursor",
        }

        data = {
            "model": "acp/cursor",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        result = route_acp_request(data=data, acp_client=mock_client)
        mock_client.chat.assert_called_once()
        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["messages"] == data["messages"]
        assert result["object"] == "chat.completion"

    def test_route_acp_request_strips_acp_prefix_from_model(self):
        """route_acp_request strips 'acp/' prefix from model name before passing to chat."""
        from acp.routing import route_acp_request

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "id": "acp-6",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": "cursor",
        }
        data = {"model": "acp/cursor-1.5", "messages": [{"role": "user", "content": "q"}]}
        route_acp_request(data=data, acp_client=mock_client)
        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["model"] == "cursor-1.5"

    def test_route_acp_request_raises_on_backend_error(self):
        """route_acp_request propagates ACPBackendError as HTTPException 502."""
        from acp.routing import route_acp_request
        from fastapi import HTTPException

        mock_client = MagicMock()
        mock_client.chat.side_effect = ACPBackendError("backend crashed")

        data = {"model": "acp/cursor", "messages": [{"role": "user", "content": "hi"}]}
        with pytest.raises(HTTPException) as exc_info:
            route_acp_request(data=data, acp_client=mock_client)
        assert exc_info.value.status_code == 502

    def test_route_acp_request_model_without_prefix(self):
        """route_acp_request works when model has no 'acp/' prefix (pass-through)."""
        from acp.routing import route_acp_request

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "id": "acp-7",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "yes"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            "model": "cursor",
        }
        data = {"model": "cursor", "messages": [{"role": "user", "content": "q"}]}
        route_acp_request(data=data, acp_client=mock_client)
        call_kwargs = mock_client.chat.call_args[1]
        assert call_kwargs["model"] == "cursor"


# ---------------------------------------------------------------------------
# is_acp_model helper
# ---------------------------------------------------------------------------

class TestIsACPModel:
    def test_acp_prefix_is_acp_model(self):
        from acp.routing import is_acp_model
        assert is_acp_model("acp/cursor") is True
        assert is_acp_model("acp/claude-3") is True

    def test_non_acp_prefix_is_not_acp_model(self):
        from acp.routing import is_acp_model
        assert is_acp_model("gpt-4") is False
        assert is_acp_model("openai/gpt-4") is False
        assert is_acp_model("") is False
        assert is_acp_model(None) is False
