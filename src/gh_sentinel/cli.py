"""
cli.py — Command-line interface for gh-sentinel.

Commands:
  watch    Continuous monitoring loop
  check    One-shot check, print new events
  status   Show monitored repos and last check info
  history  Show recent events from the store
"""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
import yaml

from .dedup import EventStore
from .formatter import format_alert, format_summary
from .monitor import RepoMonitor


def _load_config(config_path: str) -> dict:
    """Load and validate a YAML config file."""
    path = Path(config_path)
    if not path.exists():
        raise click.ClickException(f"Config file not found: {config_path}")
    with open(path) as f:
        config = yaml.safe_load(f)
    if not config:
        raise click.ClickException("Config file is empty")
    if "repos" not in config or not config["repos"]:
        raise click.ClickException("Config must have at least one repo under 'repos:'")
    return config


def _build_alerts(config: dict) -> list:
    """Build alert channel instances from config."""
    alerts = []
    alert_cfg = config.get("alerts", {})

    if "signal" in alert_cfg:
        from .alerts.signal import SignalAlert
        sig = alert_cfg["signal"]
        alerts.append(SignalAlert(
            account=sig["account"],
            recipient=sig["recipient"],
            url=sig.get("url", "http://127.0.0.1:19756"),
        ))

    if "slack" in alert_cfg:
        from .alerts.slack import SlackAlert
        slk = alert_cfg["slack"]
        alerts.append(SlackAlert(webhook_url=slk["webhook_url"]))

    if "email" in alert_cfg:
        from .alerts.email import EmailAlert
        em = alert_cfg["email"]
        alerts.append(EmailAlert(
            smtp_host=em["smtp_host"],
            smtp_port=em.get("smtp_port", 587),
            username=em["username"],
            password=em["password"],
            from_addr=em.get("from_addr", em["username"]),
            to_addr=em["to_addr"],
        ))

    return alerts


def _run_checks(config: dict, store: EventStore, verbose: bool = False) -> tuple[int, list[str]]:
    """
    Run all configured checks. Return (new_event_count, repos_checked).
    """
    monitor = RepoMonitor()
    repos = config["repos"]
    check_cfg = config.get("check", {})

    check_issues = check_cfg.get("issues", True)
    check_prs = check_cfg.get("pull_requests", True)
    check_ci = check_cfg.get("ci_status", True)
    check_dep = check_cfg.get("dependabot", True)

    all_new_events = []
    repos_with_events = []

    for repo in repos:
        if verbose:
            click.echo(f"  Checking {repo}...")
        events = monitor.check_all(
            repo,
            check_issues=check_issues,
            check_prs=check_prs,
            check_ci=check_ci,
            check_dependabot=check_dep,
        )
        new_events = store.filter_new(events)
        if new_events:
            all_new_events.extend(new_events)
            repos_with_events.append(repo)

    if all_new_events:
        store.mark_seen(all_new_events, notified=True)
        text = format_alert(all_new_events)
        click.echo(text)

        # Send to all configured alert channels
        alert_channels = _build_alerts(config)
        for channel in alert_channels:
            try:
                channel.send(text)
                if verbose:
                    click.echo(f"  ✓ Alert sent via {type(channel).__name__}")
            except Exception as e:
                click.echo(f"  ⚠ Alert failed ({type(channel).__name__}): {e}", err=True)

    return len(all_new_events), repos_with_events


@click.group()
def cli():
    """gh-sentinel — GitHub Activity Monitor."""
    pass


@cli.command()
@click.option("--config", "-c", required=True, help="Path to config YAML file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def watch(config: str, verbose: bool):
    """Continuous monitoring loop. Runs until Ctrl-C."""
    cfg = _load_config(config)
    interval = cfg.get("check_interval", 300)
    repos = cfg["repos"]

    click.echo(f"🔭 gh-sentinel watching {len(repos)} repo(s) every {interval}s")
    click.echo(f"   Repos: {', '.join(repos)}")
    click.echo("   Press Ctrl-C to stop\n")

    with EventStore() as store:
        while True:
            try:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                if verbose:
                    click.echo(f"[{now}] Checking...")

                new_count, repos_checked = _run_checks(cfg, store, verbose=verbose)
                summary = format_summary(new_count, repos)
                click.echo(f"[{now}] {summary}")

                time.sleep(interval)
            except KeyboardInterrupt:
                click.echo("\nStopped.")
                break


@cli.command()
@click.option("--config", "-c", required=True, help="Path to config YAML file")
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
def check(config: str, verbose: bool):
    """One-shot check — print new events and exit."""
    cfg = _load_config(config)
    repos = cfg["repos"]

    click.echo(f"Checking {len(repos)} repo(s)...")
    if verbose:
        for r in repos:
            click.echo(f"  • {r}")
    click.echo("")

    with EventStore() as store:
        new_count, repos_with_events = _run_checks(cfg, store, verbose=verbose)
        summary = format_summary(new_count, repos)
        click.echo(f"\n{summary}")

    sys.exit(0 if new_count == 0 else 1)


@cli.command()
def status():
    """Show event store statistics."""
    with EventStore() as store:
        stats = store.get_stats()
        click.echo(f"Total events seen:   {stats['total']}")
        click.echo(f"Alerts sent:         {stats['notified']}")
        click.echo("")
        if stats["by_type"]:
            click.echo("By type:")
            for etype, count in sorted(stats["by_type"].items()):
                click.echo(f"  {etype:12s} {count}")
        else:
            click.echo("No events recorded yet.")


@cli.command()
@click.option("--last", "-n", default=20, show_default=True, help="Number of events to show")
def history(last: int):
    """Show recent events from the store."""
    with EventStore() as store:
        rows = store.get_recent(limit=last)

    if not rows:
        click.echo("No events in history yet.")
        return

    click.echo(f"{'TYPE':<12} {'REPO':<35} {'ID':<8} {'TITLE':<45} NOTIFIED")
    click.echo("-" * 110)
    for row in rows:
        title = row["title"][:44]
        notified = "✓" if row["notified"] else "·"
        click.echo(
            f"{row['event_type']:<12} {row['repo']:<35} "
            f"#{row['event_id']:<7} {title:<45} {notified}"
        )
