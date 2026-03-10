"""
Slack alert channel via Incoming Webhooks.

Create a webhook at: https://api.slack.com/messaging/webhooks
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass
class SlackAlert:
    """Send alerts to a Slack channel via Incoming Webhook."""

    webhook_url: str
    username: str = "gh-sentinel"
    icon_emoji: str = ":satellite:"

    def send(self, message: str) -> None:
        """Post a message to Slack."""
        payload = json.dumps({
            "text": message,
            "username": self.username,
            "icon_emoji": self.icon_emoji,
        }).encode()

        req = urllib.request.Request(
            self.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
                if body != "ok":
                    raise RuntimeError(f"Slack returned unexpected response: {body}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"Slack webhook HTTP {e.code}: {e.reason}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"Slack not reachable: {e}") from e
