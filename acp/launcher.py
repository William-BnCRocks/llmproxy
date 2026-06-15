"""ACP Launcher - manages lifecycle of ACP backend processes (Cursor first).

Handles spawning, stdio pipes, auto-restart on crash, structured logging.
Reference pattern: similar to Hermes MCP client process management but for ACP protocol.
"""

import subprocess
import time
import logging
import os
from typing import Optional
from .config import ACPConfig

logger = logging.getLogger(__name__)


class ACPLauncher:
    """Launches and manages an ACP backend process."""

    def __init__(self, config: ACPConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self._restart_count = 0

    def start(self) -> subprocess.Popen:
        """Start the ACP backend process with stdio pipes."""
        if self.process and self.process.poll() is None:
            logger.info("Process already running")
            return self.process

        cmd = self.config.command + self.config.args
        env = {**os.environ, **self.config.env}

        logger.info(f"Starting ACP backend: {cmd}")
        self.process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding='utf-8',
            bufsize=1,  # line buffered
        )
        logger.info(f"ACP process started with PID {self.process.pid}")
        return self.process

    def stop(self) -> None:
        """Stop the running process gracefully."""
        if self.process:
            logger.info("Stopping ACP process")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def restart(self) -> subprocess.Popen:
        """Restart the process (for auto-restart logic)."""
        self.stop()
        time.sleep(self.config.restart_delay)
        self._restart_count += 1
        logger.info(f"Restarting ACP backend (attempt #{self._restart_count})")
        return self.start()

    def is_running(self) -> bool:
        """Check if the process is still alive."""
        return self.process is not None and self.process.poll() is None
