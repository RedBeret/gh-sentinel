"""Tests for dedup.py — SQLite event store."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from gh_sentinel.dedup import EventStore
from gh_sentinel.monitor import Event


def make_event(eid="1", etype="issue", repo="owner/repo", title="Test") -> Event:
    return Event(
        event_id=eid,
        event_type=etype,
        repo=repo,
        title=title,
        url=f"https://github.com/{repo}/issues/{eid}",
        created_at="2026-03-01T10:00:00Z",
        state="open",
    )


@pytest.fixture
def store(tmp_path):
    """EventStore backed by a temp directory."""
    db_path = tmp_path / "events.db"
    s = EventStore(db_path=db_path)
    yield s
    s.close()


class TestEventStore:
    def test_new_event_is_new(self, store):
        event = make_event("1")
        assert store.is_new(event) is True

    def test_seen_event_not_new(self, store):
        event = make_event("1")
        store.mark_seen([event])
        assert store.is_new(event) is False

    def test_different_id_is_new(self, store):
        event1 = make_event("1")
        event2 = make_event("2")
        store.mark_seen([event1])
        assert store.is_new(event2) is True

    def test_different_type_is_new(self, store):
        """Same event_id but different type = different event."""
        issue = make_event("1", etype="issue")
        pr = make_event("1", etype="pr")
        store.mark_seen([issue])
        assert store.is_new(pr) is True

    def test_different_repo_is_new(self, store):
        event1 = make_event("1", repo="owner/repo1")
        event2 = make_event("1", repo="owner/repo2")
        store.mark_seen([event1])
        assert store.is_new(event2) is True

    def test_filter_new_removes_seen(self, store):
        events = [make_event(str(i)) for i in range(5)]
        store.mark_seen(events[:3])
        new = store.filter_new(events)
        assert len(new) == 2
        assert {e.event_id for e in new} == {"3", "4"}

    def test_filter_new_empty_input(self, store):
        assert store.filter_new([]) == []

    def test_mark_seen_idempotent(self, store):
        event = make_event("1")
        store.mark_seen([event])
        store.mark_seen([event])  # No error — INSERT OR IGNORE
        assert store.is_new(event) is False

    def test_dedup_prevents_double_alert(self, store):
        """Simulates the same event arriving in two consecutive checks."""
        event = make_event("42")
        # First check: new
        new1 = store.filter_new([event])
        assert len(new1) == 1
        store.mark_seen(new1)
        # Second check: already seen
        new2 = store.filter_new([event])
        assert len(new2) == 0

    def test_get_recent(self, store):
        events = [make_event(str(i)) for i in range(5)]
        store.mark_seen(events)
        recent = store.get_recent(limit=3)
        assert len(recent) == 3

    def test_get_recent_empty(self, store):
        assert store.get_recent() == []

    def test_get_stats_empty(self, store):
        stats = store.get_stats()
        assert stats["total"] == 0
        assert stats["notified"] == 0
        assert stats["by_type"] == {}

    def test_get_stats_counts(self, store):
        issues = [make_event(str(i), etype="issue") for i in range(3)]
        prs = [make_event(str(i), etype="pr") for i in range(2)]
        store.mark_seen(issues, notified=True)
        store.mark_seen(prs, notified=False)
        stats = store.get_stats()
        assert stats["total"] == 5
        assert stats["notified"] == 3
        assert stats["by_type"]["issue"] == 3
        assert stats["by_type"]["pr"] == 2

    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "cm_test.db"
        with EventStore(db_path=db_path) as store:
            event = make_event("1")
            store.mark_seen([event])
        # Re-open and verify persistence
        with EventStore(db_path=db_path) as store2:
            assert store2.is_new(event) is False

    def test_batch_mark_seen(self, store):
        events = [make_event(str(i)) for i in range(10)]
        store.mark_seen(events)
        for event in events:
            assert store.is_new(event) is False
