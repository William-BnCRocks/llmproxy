"""Tests for acp/client.py — error handling when backend not running."""

import pytest
from unittest.mock import MagicMock, patch

from acp.client import ACPClient, ACPBackendError
from acp.config import ACPConfig


@pytest.fixture
def config():
    return ACPConfig(backend="cursor", command=["cursor", "--acp"], args=[])


def test_connect_raises_when_command_not_found(config):
    """connect() raises ACPBackendError if the backend binary is missing."""
    bad_config = ACPConfig(
        backend="cursor", command=["nonexistent_binary_xyz"], args=[]
    )
    client = ACPClient(bad_config)
    with pytest.raises(ACPBackendError, match="not found"):
        client.connect()


def test_send_request_raises_when_not_running(config):
    """_send_request raises ACPBackendError when backend is not running."""
    client = ACPClient(config)
    with pytest.raises(ACPBackendError, match="not running"):
        client._send_request("test_method", {})


def test_connect_raises_when_process_exits_immediately(config):
    """connect() raises ACPBackendError if the process exits right after start."""
    client = ACPClient(config)
    mock_launcher = MagicMock()
    # is_running returns True first (survives start()) then False (exits immediately)
    mock_launcher.is_running.side_effect = [True, False]
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="exited immediately"):
        client.connect()


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
    """_send_request raises ACPBackendError when backend closes stdout."""
    client = ACPClient(config)
    mock_launcher = MagicMock()
    mock_proc = MagicMock()
    mock_proc.stdin.write.return_value = None
    mock_proc.stdin.flush.return_value = None
    mock_proc.stdout.readline.return_value = ""  # EOF
    mock_launcher.is_running.return_value = True
    mock_launcher.process = mock_proc
    client._launcher = mock_launcher
    with pytest.raises(ACPBackendError, match="closed stdout"):
        client._send_request("test", {})
