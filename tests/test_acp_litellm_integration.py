"""tests/test_acp_litellm_integration.py

TDD — Task 5: Wire ACP backend into litellm.completion() provider dispatch.

Tests are written FIRST (RED). They verify:
1. litellm.completion() with custom_llm_provider="acp" routes through ACPClient.
2. The ACPConfig is sourced from litellm_params or env.
3. ModelResponse is returned (OpenAI-compatible).
4. ACPBackendError is surfaced as a LiteLLMException / propagated.
5. acp/routing.is_acp_model() detects "acp/<model>" prefix strings.

Run to confirm RED:
    pytest tests/test_acp_litellm_integration.py -q --tb=short

Then implement acp provider branch in litellm/main.py and re-run for GREEN.
"""

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: minimal OpenAI-compatible chat.completion dict
# ---------------------------------------------------------------------------

def _mock_acp_response(content: str = "Hello from ACP") -> Dict[str, Any]:
    return {
        "id": "acp-test-001",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "cursor-default",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
    }


# ---------------------------------------------------------------------------
# Unit: acp routing helpers
# ---------------------------------------------------------------------------

class TestIsACPModelHelper:
    """Verify is_acp_model covers all detection cases."""

    def test_acp_slash_prefix_detected(self):
        from acp.routing import is_acp_model
        assert is_acp_model("acp/cursor") is True

    def test_acp_slash_submodel_detected(self):
        from acp.routing import is_acp_model
        assert is_acp_model("acp/claude-3-5-sonnet") is True

    def test_plain_model_not_acp(self):
        from acp.routing import is_acp_model
        assert is_acp_model("gpt-4o") is False
        assert is_acp_model("openai/gpt-4") is False
        assert is_acp_model("cursor") is False

    def test_none_not_acp(self):
        from acp.routing import is_acp_model
        assert is_acp_model(None) is False

    def test_empty_string_not_acp(self):
        from acp.routing import is_acp_model
        assert is_acp_model("") is False


# ---------------------------------------------------------------------------
# Unit: route_acp_request via mock client
# ---------------------------------------------------------------------------

class TestRouteACPRequestIntegration:
    """route_acp_request translates litellm data dict → ACPClient.chat."""

    def test_full_roundtrip_with_mocked_client(self):
        from acp.routing import route_acp_request

        mock_client = MagicMock()
        mock_client.chat.return_value = _mock_acp_response("hi")

        data = {
            "model": "acp/cursor",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.5,
        }
        result = route_acp_request(data=data, acp_client=mock_client)

        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "hi"
        call_kw = mock_client.chat.call_args[1]
        assert call_kw["model"] == "cursor"          # prefix stripped
        assert call_kw["messages"] == data["messages"]
        assert call_kw["temperature"] == 0.5

    def test_backend_error_raises_http_502(self):
        from acp.routing import route_acp_request
        from acp.client import ACPBackendError
        from fastapi import HTTPException

        mock_client = MagicMock()
        mock_client.chat.side_effect = ACPBackendError("process died")

        with pytest.raises(HTTPException) as exc_info:
            route_acp_request(
                data={"model": "acp/cursor", "messages": [{"role": "user", "content": "q"}]},
                acp_client=mock_client,
            )
        assert exc_info.value.status_code == 502
        assert "ACP backend error" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Integration: litellm.completion() dispatch with custom_llm_provider="acp"
# ---------------------------------------------------------------------------

class TestLiteLLMCompletionACPDispatch:
    """
    Verify that litellm.completion() routes to ACP when
    custom_llm_provider="acp" (or model="acp/<name>").

    Uses a double-patch strategy:
    - patch acp.client.ACPClient so no real process is spawned
    - patch acp.routing.route_acp_request to capture the call and return a
      known ModelResponse-compatible dict

    This is an integration test against the routing branch; the ACPClient
    unit tests cover the full JSON-RPC lifecycle separately.
    """

    def test_completion_routes_to_acp_when_custom_provider_set(self):
        """litellm.completion with custom_llm_provider='acp' returns a ModelResponse."""
        import litellm
        from litellm import ModelResponse
        from acp.config import ACPConfig

        fake_response = _mock_acp_response("ACP reply")

        with patch("litellm.main._acp_completion") as mock_acp_completion:
            mock_acp_completion.return_value = ModelResponse(**fake_response)

            result = litellm.completion(
                model="cursor-default",
                messages=[{"role": "user", "content": "hi"}],
                custom_llm_provider="acp",
                acp_config=ACPConfig(
                    backend="cursor",
                    command=["echo", "mock"],
                    args=[],
                ),
            )

        mock_acp_completion.assert_called_once()
        assert isinstance(result, ModelResponse)
        assert result.choices[0].message.content == "ACP reply"

    def test_completion_routes_to_acp_via_model_prefix(self):
        """litellm.completion with model='acp/<name>' auto-routes to ACP provider."""
        import litellm
        from litellm import ModelResponse
        from acp.config import ACPConfig

        fake_response = _mock_acp_response("prefix reply")

        with patch("litellm.main._acp_completion") as mock_acp_completion:
            mock_acp_completion.return_value = ModelResponse(**fake_response)

            result = litellm.completion(
                model="acp/cursor-default",
                messages=[{"role": "user", "content": "test"}],
                acp_config=ACPConfig(
                    backend="cursor",
                    command=["echo", "mock"],
                    args=[],
                ),
            )

        mock_acp_completion.assert_called_once()
        assert isinstance(result, ModelResponse)
        assert result.choices[0].message.content == "prefix reply"

    def test_acp_completion_helper_calls_route_acp_request(self):
        """_acp_completion() calls route_acp_request with a connected ACPClient."""
        from litellm.llms.acp.completion import acp_completion
        from acp.config import ACPConfig

        fake_response = _mock_acp_response("direct")

        with patch("litellm.llms.acp.completion.ACPClient") as MockClient:
            instance = MockClient.return_value.__enter__.return_value
            instance.chat.return_value = fake_response

            result = acp_completion(
                model="cursor-default",
                messages=[{"role": "user", "content": "hi"}],
                acp_config=ACPConfig(
                    backend="cursor",
                    command=["echo", "mock"],
                    args=[],
                ),
            )

        MockClient.assert_called_once()
        instance.chat.assert_called_once()
        assert result["object"] == "chat.completion"
        assert result["choices"][0]["message"]["content"] == "direct"

    def test_acp_completion_helper_raises_on_missing_config(self):
        """_acp_completion() raises ValueError when no acp_config is supplied."""
        from litellm.llms.acp.completion import acp_completion

        with pytest.raises((ValueError, TypeError)):
            acp_completion(
                model="cursor",
                messages=[{"role": "user", "content": "hi"}],
                acp_config=None,
            )


# ---------------------------------------------------------------------------
# Config: ACPConfig from proxy model_list litellm_params
# ---------------------------------------------------------------------------

class TestACPConfigFromLitellmParams:
    """ACPConfig can be constructed from a proxy model_list litellm_params dict."""

    def test_acp_config_round_trip_from_dict(self):
        from acp.config import ACPConfig

        params = {
            "backend": "cursor",
            "command": ["cursor", "--acp"],
            "args": ["--stdio"],
            "env": {"CURSOR_API_KEY": "sk-test"},
        }
        cfg = ACPConfig(**params)
        assert cfg.backend == "cursor"
        assert cfg.command == ["cursor", "--acp"]
        assert cfg.args == ["--stdio"]
        assert cfg.env == {"CURSOR_API_KEY": "sk-test"}

    def test_acp_config_defaults(self):
        from acp.config import ACPConfig

        cfg = ACPConfig(backend="claude", command=["claude", "--acp"], args=[])
        assert cfg.auto_restart is True
        assert cfg.restart_delay == 1.0
        assert cfg.env == {}
