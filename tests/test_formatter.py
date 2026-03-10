"""Tests for formatter.py."""

from __future__ import annotations

import pytest

from gh_sentinel.formatter import format_alert, format_summary
from gh_sentinel.monitor import Event


def make_event(eid, etype, repo, title, state="open", url=None, extra=None) -> Event:
    return Event(
        event_id=eid,
        event_type=etype,
        repo=repo,
        title=title,
        url=url or f"https://github.com/{repo}/{etype}s/{eid}",
        created_at="2026-03-01T10:00:00Z",
        state=state,
        extra=extra or {},
    )


class TestFormatAlert:
    def test_empty_returns_no_new(self):
        result = format_alert([])
        assert result == "No new events."

    def test_single_issue(self):
        events = [make_event("1", "issue", "owner/repo", "Bug: crash")]
        result = format_alert(events)
        assert "owner/repo" in result
        assert "[issue]" in result
        assert "#1" in result
        assert "Bug: crash" in result
        assert "🐛" in result

    def test_single_pr(self):
        events = [make_event("5", "pr", "owner/repo", "Add feature", state="draft")]
        result = format_alert(events)
        assert "[pr]" in result
        assert "#5" in result
        assert "🔀" in result
        assert "draft" in result

    def test_ci_failure(self):
        events = [make_event("999", "ci", "owner/repo", "CI on main", state="failure")]
        result = format_alert(events)
        assert "[ci]" in result
        assert "❌" in result
        assert "failed" in result

    def test_dependabot_with_severity(self):
        events = [make_event(
            "3", "dependabot", "owner/repo",
            "Prototype pollution in lodash",
            state="open",
            extra={"severity": "high", "package": "lodash"},
        )]
        result = format_alert(events)
        assert "[dependabot]" in result
        assert "🔒" in result
        assert "high" in result
        assert "lodash" in result

    def test_grouped_by_repo(self):
        events = [
            make_event("1", "issue", "owner/repo-a", "Issue A"),
            make_event("2", "issue", "owner/repo-b", "Issue B"),
        ]
        result = format_alert(events)
        lines = result.split("\n")
        # repo-a should appear before repo-b (sorted)
        a_idx = next(i for i, l in enumerate(lines) if "repo-a" in l)
        b_idx = next(i for i, l in enumerate(lines) if "repo-b" in l)
        assert a_idx < b_idx

    def test_grouped_by_type_within_repo(self):
        events = [
            make_event("5", "pr", "owner/repo", "PR title"),
            make_event("1", "issue", "owner/repo", "Issue title"),
        ]
        result = format_alert(events)
        # Issues should come before PRs (type order: issue, pr, ci, dependabot)
        issue_idx = result.index("[issue]")
        pr_idx = result.index("[pr]")
        assert issue_idx < pr_idx

    def test_title_truncation(self):
        long_title = "A" * 100
        events = [make_event("1", "issue", "owner/repo", long_title)]
        result = format_alert(events, max_title_len=30)
        # Should be truncated with ellipsis
        assert "…" in result

    def test_url_appears(self):
        events = [make_event("1", "issue", "owner/repo", "Bug", url="https://example.com/1")]
        result = format_alert(events)
        assert "https://example.com/1" in result

    def test_multiple_events_same_repo(self):
        events = [
            make_event("1", "issue", "owner/repo", "Bug 1"),
            make_event("2", "issue", "owner/repo", "Bug 2"),
            make_event("5", "pr", "owner/repo", "PR title"),
        ]
        result = format_alert(events)
        # Only one repo header
        assert result.count("owner/repo:") == 1
        assert result.count("[issue]") == 2
        assert result.count("[pr]") == 1


class TestFormatSummary:
    def test_no_new_events(self):
        result = format_summary(0, ["owner/repo-a", "owner/repo-b"])
        assert "No new events" in result
        assert "2 repo" in result

    def test_with_new_events(self):
        result = format_summary(3, ["owner/repo"])
        assert "3 new event" in result
        assert "owner/repo" in result

    def test_multiple_repos_in_summary(self):
        result = format_summary(5, ["a/b", "c/d", "e/f"])
        assert "3 repo" in result
