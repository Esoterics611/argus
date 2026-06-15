#!/usr/bin/env bash
# Idempotent bootstrap for Argus dev environment.
# Run from the repo root: bash scripts/init_env.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

log() { echo "[init_env] $*"; }

# ── uv ──────────────────────────────────────────────────────────────────────
if ! command -v uv &>/dev/null; then
  log "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.cargo/bin:$PATH"
else
  log "uv already installed ($(uv --version))"
fi

# ── Python deps ─────────────────────────────────────────────────────────────
log "Syncing Python deps..."
uv sync --all-extras

# ── Playwright Chromium ──────────────────────────────────────────────────────
log "Installing Playwright Chromium..."
uv run playwright install chromium --with-deps

# ── Patchright Chromium (CDP-leak patched fork) ──────────────────────────────
log "Installing Patchright Chromium..."
uv run patchright install chromium --with-deps

# ── Camoufox (Firefox fork with C++-level fingerprint spoofing) ──────────────
log "Fetching Camoufox..."
uv run python -c "from camoufox.sync_api import Camoufox; print('camoufox ok')" 2>/dev/null \
  || uv run camoufox fetch

# ── Docker services ──────────────────────────────────────────────────────────
if command -v docker &>/dev/null && command -v docker compose &>/dev/null; then
  log "Starting QuestDB + NATS via docker compose..."
  docker compose up -d
  log "Services up. QuestDB UI → http://localhost:9000"
else
  log "WARNING: docker not found — skipping QuestDB + NATS startup."
  log "  Install Docker Desktop or run: sudo apt install docker.io docker-compose-v2"
fi

# ── .env ────────────────────────────────────────────────────────────────────
if [ ! -f .env ]; then
  log "Creating .env from .env.example (fill in your proxy creds)..."
  cp .env.example .env
else
  log ".env already exists — skipping."
fi

# ── data dirs ───────────────────────────────────────────────────────────────
mkdir -p data/parquet traces/har traces/trace site

log ""
log "Bootstrap complete."
log "  Run tests : uv run pytest"
log "  CLI       : uv run argus --help"
log "  Harvest   : uv run argus harvest news"
