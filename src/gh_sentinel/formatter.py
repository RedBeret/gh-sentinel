"""
formatter.py — Format GitHub events as human-readable alert text.

Groups events by repo and type for a clean, scannable digest.
"""

from __future__ import annotations

from collections import defaultdict

from .monitor import Event


_TYPE_ICONS = {
    "issue": "🐛",
    "pr": "🔀",
    "ci": "❌",
    "dependabot": "🔒",
}

_STATE_LABELS = {
    "open": "open",
    "draft": "draft",
    "failure": "failed",
    "timed_out": "timed out",
    "startup_failure": "startup failed",
    "in_progress": "running",
}


def format_alert(events: list[Event], max_title_len: int = 70) -> str:
    """
    Format a list of events into a human-readable alert string.

    Groups events by repo and then by type:

        owner/backend:
          🐛 [issue] #3: Bug in encryption (open)
          🔀 [pr] #5: Add PBKDF2 support (open)
        owner/frontend:
          ❌ [ci] CI on main — failed
    """
    if not events:
        return "No new events."

    # Group: repo → event_type → list[Event]
    grouped: dict[str, dict[str, list[Event]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        grouped[event.repo][event.event_type].append(event)

    type_order = ["issue", "pr", "ci", "dependabot"]
    lines: list[str] = []

    for repo in sorted(grouped):
        lines.append(f"{repo}:")
        by_type = grouped[repo]

        for etype in type_order:
            if etype not in by_type:
                continue
            for event in by_type[etype]:
                icon = _TYPE_ICONS.get(etype, "•")
                title = event.title
                if len(title) > max_title_len:
                    title = title[:max_title_len - 1] + "…"
                state = _STATE_LABELS.get(event.state, event.state)

                if etype in ("issue", "pr"):
                    label = f"#{event.event_id}: {title}"
                    if state:
                        label += f" ({state})"
                elif etype == "ci":
                    label = f"{title}"
                    if state:
                        label += f" — {state}"
                elif etype == "dependabot":
                    severity = event.extra.get("severity", "")
                    pkg = event.extra.get("package", "")
                    label = title
                    if pkg:
                        label += f" ({pkg})"
                    if severity:
                        label += f" [{severity}]"
                else:
                    label = title

                lines.append(f"  {icon} [{etype}] {label}")
                lines.append(f"    {event.url}")

        lines.append("")

    # Remove trailing blank line
    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def format_summary(new_count: int, repos_checked: list[str]) -> str:
    """One-line summary for logs."""
    if new_count == 0:
        return f"✓ No new events across {len(repos_checked)} repo(s)"
    return (
        f"🔔 {new_count} new event(s) across "
        f"{len(repos_checked)} repo(s): "
        + ", ".join(repos_checked)
    )
