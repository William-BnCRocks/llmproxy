"""acp/client.py

High-level ACP client: launches backend via ACPLauncher and performs
JSON-RPC handshake.  All public calls raise ACPBackendError if the
backend process is not running or becomes unreachable mid-session.
"""

import concurrent.futures
import json
import logging
from typing import Any, Dict, List, Optional

from .config import ACPConfig
from .launcher import ACPLauncher

logger = logging.getLogger(__name__)


class ACPBackendError(RuntimeError):
    """Raised when the ACP backend process is not running or unreachable."""


class ACPClient:
    """High-level ACP client over stdio JSON-RPC.

    Usage::

        # Direct lifecycle:
        client = ACPClient(config)
        client.connect()         # start backend + handshake
        reply = client.chat(messages=[{"role": "user", "content": "Hi"}])
        client.disconnect()      # clean shutdown

        # Context manager (preferred):
        with ACPClient(config) as client:
            reply = client.chat(messages=[{"role": "user", "content": "Hi"}])

    ``chat()`` returns the assistant's text string extracted from the first
    choice.  Additional keyword arguments (``temperature``, ``max_tokens``,
    etc.) are forwarded verbatim in the JSON-RPC params.
    """

    def __init__(self, config: ACPConfig):
        self.config = config
        self._launcher = ACPLauncher(config)
        self._request_id = 0

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "ACPClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
        return None  # do not suppress exceptions

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Start the backend process and perform the ACP initialize handshake.

        Raises:
            ACPBackendError: if the backend command is not found, fails to
                start, exits immediately, or the handshake is rejected.
        """
        if not self._launcher.is_running():
            try:
                self._launcher.start()
            except FileNotFoundError as exc:
                raise ACPBackendError(
                    f"ACP backend command not found: {self.config.command!r}"
                ) from exc
            except OSError as exc:
                raise ACPBackendError(
                    f"Failed to start ACP backend: {exc}"
                ) from exc

        # Guard: process may have exited immediately (bad command / config)
        if not self._launcher.is_running():
            raise ACPBackendError(
                "ACP backend process exited immediately after start — "
                "check command and args in ACPConfig"
            )

        self._handshake()

    def disconnect(self) -> None:
        """Stop the ACP backend process gracefully."""
        self._launcher.stop()

    def is_connected(self) -> bool:
        """Return True if the backend process is currently running."""
        return self._launcher.is_running()

    # ------------------------------------------------------------------
    # High-level API
    # ------------------------------------------------------------------

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Send a chat completion request to the ACP backend.

        Translates OpenAI-style chat arguments into a JSON-RPC
        ``chat/complete`` call and returns the full OpenAI-compatible
        response dict from the backend.

        Args:
            messages: List of ``{"role": ..., "content": ...}`` dicts.
            model: Model identifier forwarded to the ACP backend.
            timeout: Optional per-call timeout in seconds.  If the backend
                does not respond within this window, raises ACPBackendError.
            **kwargs: Extra params forwarded verbatim (e.g. temperature,
                max_tokens).

        Returns:
            OpenAI-compatible ``chat.completion`` dict (the ``result``
            field of the JSON-RPC response).

        Raises:
            ACPBackendError: if the backend is not running, the pipe breaks,
                or the backend returns a JSON-RPC error.
        """
        params: Dict[str, Any] = {"model": model, "messages": messages, **kwargs}
        response = self._send_request("chat/complete", params, timeout=timeout)
        # _send_request already raises ACPBackendError on JSON-RPC error objects;
        # return the result payload directly.
        return response.get("result", response)

    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _send_request(
        self,
        method: str,
        params: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Send a single JSON-RPC request and read the response line.

        Args:
            method: JSON-RPC method name.
            params: JSON-RPC params dict.
            timeout: Optional timeout in seconds for the full round-trip.
                Raises ACPBackendError with "timed out" in the message when
                the backend does not respond within the budget.

        Raises:
            ACPBackendError: if the backend is not running, pipe breaks,
                the backend closes stdout unexpectedly, the response is not
                valid JSON, the response contains a JSON-RPC error object,
                or the call times out.
        """
        if not self._launcher.is_running():
            raise ACPBackendError(
                "ACP backend is not running — call connect() first"
            )
        proc = self._launcher.process
        if proc is None:
            raise ACPBackendError("ACP backend process is None — not started")
        assert proc.stdin is not None and proc.stdout is not None
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        try:
            proc.stdin.write(json.dumps(req) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise ACPBackendError(f"ACP backend pipe error: {exc}") from exc

        # Read response with optional timeout via a thread so we can interrupt
        # the blocking readline() without needing async I/O.
        def _read_line() -> str:
            return proc.stdout.readline()  # type: ignore[union-attr]

        try:
            pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = pool.submit(_read_line)
            try:
                line = future.result(timeout=timeout)
            except concurrent.futures.TimeoutError as exc:
                # Kill and clean up so the process doesn't linger; the thread
                # is stuck in readline() which will unblock once the process
                # stdout is closed by stop().
                try:
                    self._launcher.stop()
                except Exception:
                    pass
                pool.shutdown(wait=False)
                raise ACPBackendError(
                    f"ACP backend timed out after {timeout}s — no response received"
                ) from exc
            finally:
                pool.shutdown(wait=False)
        except ACPBackendError:
            raise
        except (BrokenPipeError, OSError) as exc:
            raise ACPBackendError(f"ACP backend pipe error: {exc}") from exc

        if not line:
            raise ACPBackendError(
                "ACP backend closed stdout unexpectedly — process may have crashed"
            )

        try:
            response = json.loads(line.strip())
        except json.JSONDecodeError as exc:
            raise ACPBackendError(
                f"ACP backend returned malformed JSON: {line.strip()!r}"
            ) from exc

        # Surface JSON-RPC error objects as ACPBackendError
        if "error" in response:
            err = response["error"]
            msg = err.get("message", str(err))
            code = err.get("code", "")
            raise ACPBackendError(
                f"ACP backend returned JSON-RPC error (code {code}): {msg}"
            )

        return response

    def _handshake(self) -> None:
        """Perform the ACP initialize handshake with the backend."""
        resp = self._send_request(
            "initialize",
            {"clientInfo": {"name": "llmproxy", "version": "0.1.0"}},
        )
        logger.debug("ACP handshake response: %s", resp)
