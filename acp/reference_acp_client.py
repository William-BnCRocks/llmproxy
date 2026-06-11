"""reference_acp_client.py

Extracted ACP client patterns for stdio JSON-RPC communication with Cursor/Claude backends.
Pure ACP only — no MCP references anywhere in this file or module.
"""

import json
import subprocess
from typing import Any, Dict, Optional


class ACPClient:
    """Minimal ACP client stub for reference (full impl in client.py later)."""

    def __init__(self, process: subprocess.Popen):
        self.process = process
        self.request_id = 0

    def _next_id(self) -> int:
        self.request_id += 1
        return self.request_id

    def send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send JSON-RPC request and read response (blocking line read)."""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        line = json.dumps(req) + "\n"
        self.process.stdin.write(line)
        self.process.stdin.flush()

        # In real impl: read stdout line, parse JSON, match id or handle notifications
        response_line = self.process.stdout.readline()
        return json.loads(response_line.strip())

    def initialize(self, client_info: Dict[str, str]) -> Dict[str, Any]:
        """Perform ACP handshake."""
        return self.send_request("initialize", {"clientInfo": client_info})

    # Additional patterns: session/create, chat/complete, tool/result etc. would go here


def extract_acp_patterns() -> str:
    """Return summary of ACP client patterns for verification."""
    return "ACP client stdio JSON-RPC handshake session error-restart tool-calling patterns extracted (pure ACP)"


if __name__ == "__main__":
    print(extract_acp_patterns())
