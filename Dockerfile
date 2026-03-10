FROM python:3.12-slim

# Install gh CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

# Config and data go in mounted volumes
VOLUME ["/config", "/data"]

# gh-sentinel uses ~/.gh-sentinel for its SQLite store by default.
# Override with GH_SENTINEL_DB env var or mount /data.
ENV GH_SENTINEL_DB=/data/events.db

ENTRYPOINT ["gh-sentinel"]
CMD ["--help"]
