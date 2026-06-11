"""Tests for ACP config schema."""

from llmproxy.acp.config import ACPConfig


def test_acp_config_parsing():
    cfg = ACPConfig(backend="cursor", command=["cursor", "--acp"], args=["--stdio"])
    assert cfg.backend == "cursor"
    assert cfg.command == ["cursor", "--acp"]
    assert cfg.args == ["--stdio"]
    assert cfg.env == {}
    assert cfg.auto_restart is True
