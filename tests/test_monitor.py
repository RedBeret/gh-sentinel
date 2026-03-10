"""Tests for monitor.py — mock gh CLI output."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from gh_sentinel.monitor import Event, RepoMonitor


ISSUE_JSON = json.dumps([
    {
        "number": 1,
        "title": "Bug: crash on empty input",
        "url": "https://github.com/owner/repo/issues/1",
        "createdAt": "2026-03-01T10:00:00Z",
        "state": "OPEN",
    },
    {
        "number": 2,
        "title": "Feature request: dark mode",
        "url": "https://github.com/owner/repo/issues/2",
        "createdAt": "2026-03-02T11:00:00Z",
        "state": "OPEN",
    },
])

PR_JSON = json.dumps([
    {
        "number": 5,
        "title": "Add PBKDF2 support",
        "url": "https://github.com/owner/repo/pull/5",
        "createdAt": "2026-03-03T09:00:00Z",
        "state": "OPEN",
        "isDraft": False,
    },
    {
        "number": 6,
        "title": "WIP: refactor crypto",
        "url": "https://github.com/owner/repo/pull/6",
        "createdAt": "2026-03-04T08:00:00Z",
        "state": "OPEN",
        "isDraft": True,
    },
])

CI_JSON = json.dumps([
    {
        "databaseId": 999,
        "name": "CI",
        "headBranch": "main",
        "status": "completed",
        "conclusion": "failure",
        "createdAt": "2026-03-05T12:00:00Z",
        "url": "https://github.com/owner/repo/actions/runs/999",
    },
    {
        "databaseId": 1000,
        "name": "CI",
        "headBranch": "feat/x",
        "status": "completed",
        "conclusion": "success",
        "createdAt": "2026-03-05T11:00:00Z",
        "url": "https://github.com/owner/repo/actions/runs/1000",
    },
    {
        "databaseId": 1001,
        "name": "Lint",
        "headBranch": "main",
        "status": "in_progress",
        "conclusion": None,
        "createdAt": "2026-03-05T13:00:00Z",
        "url": "https://github.com/owner/repo/actions/runs/1001",
    },
])

DEPENDABOT_JSON = json.dumps([
    {
        "number": 3,
        "state": "open",
        "security_advisory": {
            "summary": "Prototype pollution in lodash",
            "severity": "high",
        },
        "dependency": {"package": {"name": "lodash"}},
        "html_url": "https://github.com/owner/repo/security/dependabot/3",
        "created_at": "2026-03-01T08:00:00Z",
    },
    {
        "number": 4,
        "state": "dismissed",  # Should be filtered out
        "security_advisory": {"summary": "Old issue", "severity": "low"},
        "dependency": {"package": {"name": "requests"}},
        "html_url": "https://github.com/owner/repo/security/dependabot/4",
        "created_at": "2026-02-01T08:00:00Z",
    },
])


def mock_run_gh(args, check=True):
    cmd = " ".join(args)
    if "issue list" in cmd:
        return ISSUE_JSON
    if "pr list" in cmd:
        return PR_JSON
    if "run list" in cmd:
        return CI_JSON
    if "dependabot/alerts" in cmd:
        return DEPENDABOT_JSON
    return None


class TestEvent:
    def test_composite_id(self):
        event = Event("42", "issue", "owner/repo", "title", "url", "2026-01-01")
        assert event.composite_id == "issue:owner/repo:42"

    def test_defaults(self):
        event = Event("1", "pr", "owner/repo", "title", "url", "2026-01-01")
        assert event.state == ""
        assert event.extra == {}


class TestRepoMonitor:
    def setup_method(self):
        self.monitor = RepoMonitor()

    def test_check_issues(self):
        with patch("gh_sentinel.monitor._run_gh", side_effect=mock_run_gh):
            events = self.monitor.check_issues("owner/repo")
        assert len(events) == 2
        assert events[0].event_type == "issue"
        assert events[0].event_id == "1"
        assert events[0].title == "Bug: crash on empty input"
        assert events[0].state == "open"

    def test_check_prs(self):
        with patch("gh_sentinel.monitor._run_gh", side_effect=mock_run_gh):
            events = self.monitor.check_prs("owner/repo")
        assert len(events) == 2
        assert events[0].event_type == "pr"
        assert events[0].event_id == "5"
        assert events[0].state == "open"
        assert events[1].state == "draft"

    def test_check_ci_only_failures_and_running(self):
        with patch("gh_sentinel.monitor._run_gh", side_effect=mock_run_gh):
            events = self.monitor.check_ci("owner/repo")
        # Should skip the success run
        assert len(events) == 2
        ids = {e.event_id for e in events}
        assert "999" in ids   # failure
        assert "1001" in ids  # in_progress
        assert "1000" not in ids  # success — filtered

    def test_check_ci_states(self):
        with patch("gh_sentinel.monitor._run_gh", side_effect=mock_run_gh):
            events = self.monitor.check_ci("owner/repo")
        failure_evt = next(e for e in events if e.event_id == "999")
        assert failure_evt.state == "failure"
        running_evt = next(e for e in events if e.event_id == "1001")
        assert running_evt.state == "in_progress"

    def test_check_dependabot_filters_dismissed(self):
        with patch("gh_sentinel.monitor._run_gh", side_effect=mock_run_gh):
            events = self.monitor.check_dependabot("owner/repo")
        # Only the open alert (#3), not dismissed (#4)
        assert len(events) == 1
        assert events[0].event_id == "3"
        assert events[0].event_type == "dependabot"
        assert events[0].extra["severity"] == "high"
        assert events[0].extra["package"] == "lodash"

    def test_check_all(self):
        with patch("gh_sentinel.monitor._run_gh", side_effect=mock_run_gh):
            events = self.monitor.check_all("owner/repo")
        types = {e.event_type for e in events}
        assert "issue" in types
        assert "pr" in types
        assert "ci" in types
        assert "dependabot" in types

    def test_check_all_selective(self):
        with patch("gh_sentinel.monitor._run_gh", side_effect=mock_run_gh):
            events = self.monitor.check_all(
                "owner/repo",
                check_issues=True,
                check_prs=False,
                check_ci=False,
                check_dependabot=False,
            )
        types = {e.event_type for e in events}
        assert types == {"issue"}

    def test_check_issues_returns_empty_on_failure(self):
        with patch("gh_sentinel.monitor._run_gh", return_value=None):
            events = self.monitor.check_issues("owner/repo")
        assert events == []

    def test_check_prs_returns_empty_on_failure(self):
        with patch("gh_sentinel.monitor._run_gh", return_value=None):
            events = self.monitor.check_prs("owner/repo")
        assert events == []
