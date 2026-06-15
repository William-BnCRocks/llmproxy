"""Tests for ACP Launcher (process management)."""

from acp.launcher import ACPLauncher
from acp.config import ACPConfig


def test_launcher_starts_cursor():
    """Test that launcher can start a mock ACP backend process."""
    config = ACPConfig(
        backend="cursor",
        command=["python", "-c", "import time; time.sleep(30)"],
        args=[],
        env={},
    )
    launcher = ACPLauncher(config)
    proc = launcher.start()
    assert proc.poll() is None  # still running
    launcher.stop()
