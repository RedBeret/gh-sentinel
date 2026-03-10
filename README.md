# gh-sentinel

[![CI](https://github.com/RedBeret/gh-sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/RedBeret/gh-sentinel/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**GitHub's built-in notifications are noisy. gh-sentinel deduplicates and filters for actionable events only — then delivers via Signal, Slack, or email.**

Monitor issues, pull requests, CI failures, and Dependabot alerts across your repos. Each event is only alerted *once*, even if it shows up in every check. Uses the `gh` CLI so there's no API token to manage.

## Why

- GitHub sends a notification for everything. gh-sentinel sends one alert per *new* event.
- Built on `gh` CLI — no OAuth setup, no token rotation.
- SQLite dedup store means it survives restarts without re-alerting old events.
- Zero external HTTP calls beyond GitHub itself. Signal/Slack/email are optional add-ons.
- Runs as a systemd service, macOS launchd agent, or Docker container.

## Install

```bash
pip install gh-sentinel
```

Or from source:

```bash
git clone https://github.com/RedBeret/gh-sentinel
cd gh-sentinel
pip install -e .
```

**Prerequisite:** [`gh` CLI](https://cli.github.com/) must be installed and authenticated:
```bash
gh auth login
```

## Quick Start

```bash
# 1. Copy the example config
cp examples/config.example.yaml config.yaml
# Edit config.yaml with your repos and alert channel

# 2. One-shot check (print new events, exit)
gh-sentinel check --config config.yaml

# 3. Continuous monitoring (every 5 minutes)
gh-sentinel watch --config config.yaml
```

## Configuration

```yaml
repos:
  - "myorg/backend"
  - "myorg/frontend"

check_interval: 300   # seconds between checks (for `watch` command)

check:
  issues: true
  pull_requests: true
  ci_status: true     # surfaces failures and in-progress runs
  dependabot: true    # open security alerts only

alerts:
  signal:
    account: "+1XXXXXXXXXX"    # Signal number running signal-cli daemon
    recipient: "+1YYYYYYYYYY"  # Where to send alerts
  # slack:
  #   webhook_url: "https://hooks.slack.com/services/..."
  # email:
  #   smtp_host: "smtp.gmail.com"
  #   smtp_port: 587
  #   username: "you@gmail.com"
  #   password: "your-app-password"
  #   to_addr: "you@example.com"
```

## Commands

### `gh-sentinel check`

One-shot: check all repos, print new events, exit with code 1 if any found.

```bash
gh-sentinel check --config config.yaml
gh-sentinel check --config config.yaml --verbose
```

**Example output:**
```
Checking 3 repo(s)...

RedBeret/sqlite-vault:
  🐛 [issue] #3: Bug in encryption (open)
     https://github.com/RedBeret/sqlite-vault/issues/3
  🔀 [pr] #5: Add PBKDF2 support (open)
     https://github.com/RedBeret/sqlite-vault/pull/5

RedBeret/cron-lite:
  ❌ [ci] CI on main — failed
     https://github.com/RedBeret/cron-lite/actions/runs/42

🔔 3 new event(s) across 3 repo(s)
```

### `gh-sentinel watch`

Continuous loop: checks on the configured interval, sends alerts via configured channels.

```bash
gh-sentinel watch --config config.yaml
```

Press `Ctrl-C` to stop.

### `gh-sentinel status`

Show event store statistics.

```bash
gh-sentinel status
```
```
Total events seen:   47
Alerts sent:         45

By type:
  ci           12
  dependabot    3
  issue        18
  pr           14
```

### `gh-sentinel history`

Show recent events from the local store.

```bash
gh-sentinel history --last 20
```

## Running as a Service

### systemd (Linux)

Install the provided unit file:

```bash
# Copy and edit the unit file
sudo cp examples/gh-sentinel.service /etc/systemd/system/
sudo nano /etc/systemd/system/gh-sentinel.service
# Replace 'youruser' with your username and adjust paths

# Create config directory and copy config
mkdir -p ~/.config/gh-sentinel
cp examples/config.example.yaml ~/.config/gh-sentinel/config.yaml
# Edit ~/.config/gh-sentinel/config.yaml

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now gh-sentinel

# Follow logs
journalctl -u gh-sentinel -f
```

The unit file (`examples/gh-sentinel.service`) sets `Restart=on-failure` and
logs to journald. Edit `User=`, `ExecStart=`, and the config path before installing.

### macOS launchd

Install the provided plist:

```bash
# Copy and edit the plist
cp examples/com.gh-sentinel.plist ~/Library/LaunchAgents/
# Edit the plist: replace 'youruser' with your username

# Create config and copy example
mkdir -p ~/.config/gh-sentinel
cp examples/config.example.yaml ~/.config/gh-sentinel/config.yaml
# Edit ~/.config/gh-sentinel/config.yaml

# Load the agent
launchctl load ~/Library/LaunchAgents/com.gh-sentinel.plist

# Check status
launchctl list | grep gh-sentinel

# Follow logs
tail -f ~/Library/Logs/gh-sentinel.log

# Stop
launchctl unload ~/Library/LaunchAgents/com.gh-sentinel.plist
```

The agent runs at login, restarts automatically on crashes, and logs to
`~/Library/Logs/gh-sentinel.log`.

### Docker

**Build and run:**

```bash
# Copy and configure
cp examples/config.example.yaml config.yaml
# Edit config.yaml

# One-shot check
docker build -t gh-sentinel .
docker run --rm \
  -v "$PWD/config.yaml:/config/config.yaml:ro" \
  -v "$HOME/.config/gh:/root/.config/gh:ro" \
  gh-sentinel check --config /config/config.yaml

# Continuous daemon via docker compose
docker compose up -d

# Follow logs
docker compose logs -f
```

**`docker-compose.yml`** mounts your config and persists the event store across restarts:

```yaml
services:
  gh-sentinel:
    build: .
    restart: unless-stopped
    command: watch --config /config/config.yaml
    volumes:
      - ./config.yaml:/config/config.yaml:ro
      - gh-sentinel-data:/data
      - ${HOME}/.config/gh:/root/.config/gh:ro

volumes:
  gh-sentinel-data:
```

The `GH_SENTINEL_DB` environment variable controls where the SQLite store lives
(default: `~/.gh-sentinel/events.db`; in Docker: `/data/events.db`).

## Signal Alerts

gh-sentinel uses [signal-cli](https://github.com/AsamK/signal-cli) running as a local HTTP daemon:

```bash
# Install signal-cli, then start the daemon:
signal-cli -a +1XXXXXXXXXX daemon --http 127.0.0.1:19756
```

Then configure `alerts.signal` in your config.yaml.

## Development

```bash
git clone https://github.com/RedBeret/gh-sentinel
cd gh-sentinel
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

## License

MIT — see [LICENSE](LICENSE).
