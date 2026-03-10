"""
monitor.py — Poll GitHub repos via the gh CLI.

Uses subprocess to call `gh` so no API token management is needed
beyond what's already configured in the gh CLI.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Event:
    """A single GitHub event (issue, PR, CI run, Dependabot alert)."""

    event_id: str          # Unique identifier within event_type+repo
    event_type: str        # "issue", "pr", "ci", "dependabot"
    repo: str              # "owner/repo"
    title: str
    url: str
    created_at: str        # ISO 8601
    state: str = ""        # open, closed, failed, etc.
    extra: dict = field(default_factory=dict)

    @property
    def composite_id(self) -> str:
        """Globally unique ID for deduplication."""
        return f"{self.event_type}:{self.repo}:{self.event_id}"


def _run_gh(args: list[str], check: bool = True) -> Optional[str]:
    """Run a gh CLI command and return stdout, or None on error."""
    try:
        result = subprocess.run(
            ["gh"] + args,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            if check:
                raise RuntimeError(
                    f"gh {' '.join(args)} failed: {result.stderr.strip()}"
                )
            return None
        return result.stdout
    except FileNotFoundError:
        raise RuntimeError(
            "gh CLI not found. Install from https://cli.github.com/"
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"gh command timed out: gh {' '.join(args)}")


class RepoMonitor:
    """Poll a GitHub repo for new events using the gh CLI."""

    def check_issues(self, repo: str, state: str = "open") -> list[Event]:
        """Return open issues for the repo."""
        out = _run_gh([
            "issue", "list",
            "--repo", repo,
            "--state", state,
            "--limit", "50",
            "--json", "number,title,url,createdAt,state",
        ], check=False)
        if not out:
            return []

        items = json.loads(out)
        events = []
        for item in items:
            events.append(Event(
                event_id=str(item["number"]),
                event_type="issue",
                repo=repo,
                title=item["title"],
                url=item["url"],
                created_at=item.get("createdAt", ""),
                state=item.get("state", "").lower(),
            ))
        return events

    def check_prs(self, repo: str, state: str = "open") -> list[Event]:
        """Return open pull requests for the repo."""
        out = _run_gh([
            "pr", "list",
            "--repo", repo,
            "--state", state,
            "--limit", "50",
            "--json", "number,title,url,createdAt,state,isDraft",
        ], check=False)
        if not out:
            return []

        items = json.loads(out)
        events = []
        for item in items:
            is_draft = item.get("isDraft", False)
            extra = {"is_draft": is_draft}
            events.append(Event(
                event_id=str(item["number"]),
                event_type="pr",
                repo=repo,
                title=item["title"],
                url=item["url"],
                created_at=item.get("createdAt", ""),
                state="draft" if is_draft else item.get("state", "").lower(),
                extra=extra,
            ))
        return events

    def check_ci(self, repo: str) -> list[Event]:
        """Return recent workflow runs, focusing on failures."""
        out = _run_gh([
            "run", "list",
            "--repo", repo,
            "--limit", "20",
            "--json", "databaseId,name,headBranch,status,conclusion,createdAt,url",
        ], check=False)
        if not out:
            return []

        items = json.loads(out)
        events = []
        for item in items:
            conclusion = item.get("conclusion") or ""
            status = item.get("status") or ""
            # Only surface failures and in-progress runs
            if conclusion in ("failure", "timed_out", "startup_failure") or status == "in_progress":
                events.append(Event(
                    event_id=str(item["databaseId"]),
                    event_type="ci",
                    repo=repo,
                    title=f"{item['name']} on {item.get('headBranch', 'unknown')}",
                    url=item.get("url", f"https://github.com/{repo}/actions"),
                    created_at=item.get("createdAt", ""),
                    state=conclusion or status,
                    extra={"conclusion": conclusion, "status": status},
                ))
        return events

    def check_dependabot(self, repo: str) -> list[Event]:
        """Return open Dependabot security alerts."""
        out = _run_gh([
            "api",
            f"repos/{repo}/dependabot/alerts",
            "--jq", ".[].number,.security_advisory.summary,.html_url,.created_at,.state",
        ], check=False)
        if not out:
            return []

        # gh api with --jq returns one value per line for array access
        # Use json output instead for structured parsing
        out_json = _run_gh([
            "api",
            f"repos/{repo}/dependabot/alerts",
        ], check=False)
        if not out_json:
            return []

        try:
            items = json.loads(out_json)
            if not isinstance(items, list):
                return []
        except json.JSONDecodeError:
            return []

        events = []
        for item in items:
            if item.get("state") != "open":
                continue
            advisory = item.get("security_advisory", {})
            events.append(Event(
                event_id=str(item["number"]),
                event_type="dependabot",
                repo=repo,
                title=advisory.get("summary", f"Dependabot alert #{item['number']}"),
                url=item.get("html_url", ""),
                created_at=item.get("created_at", ""),
                state=item.get("state", "open"),
                extra={
                    "severity": advisory.get("severity", "unknown"),
                    "package": item.get("dependency", {}).get("package", {}).get("name", ""),
                },
            ))
        return events

    def check_all(
        self,
        repo: str,
        check_issues: bool = True,
        check_prs: bool = True,
        check_ci: bool = True,
        check_dependabot: bool = True,
    ) -> list[Event]:
        """Check all configured event types for a repo."""
        events: list[Event] = []
        if check_issues:
            events.extend(self.check_issues(repo))
        if check_prs:
            events.extend(self.check_prs(repo))
        if check_ci:
            events.extend(self.check_ci(repo))
        if check_dependabot:
            events.extend(self.check_dependabot(repo))
        return events
