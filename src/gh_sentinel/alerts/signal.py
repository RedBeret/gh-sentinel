"""
Signal alert channel using signal-cli JSON-RPC daemon.

Requires signal-cli running as a daemon:
  signal-cli -a <account> daemon --http 127.0.0.1:19756
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class SignalAlert:
    """Send alerts via Signal using signal-cli JSON-RPC."""

    account: str      # Sending Signal number, e.g. "+15551234567"
    recipient: str    # Receiving Signal number, e.g. "+15559876543"
    url: str = "http://127.0.0.1:19756"

    def send(self, message: str) -> None:
        """Send a text message via Signal."""
        payload = json.dumps({
            "jsonrpc": "2.0",
            "method": "send",
            "params": {
                "account": self.account,
                "message": message,
                "recipient": [self.recipient],
            },
            "id": 1,
        }).encode()

        req = urllib.request.Request(
            f"{self.url}/api/v1/rpc",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read())
                if "error" in body:
                    raise RuntimeError(f"Signal error: {body['error']}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Signal daemon not reachable: {e}") from e

    def available(self) -> bool:
        """Check if signal-cli daemon is reachable."""
        try:
            urllib.request.urlopen(f"{self.url}/api/v1/rpc", timeout=2)
            return True
        except Exception:
            return False
