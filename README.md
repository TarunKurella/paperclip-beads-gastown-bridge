# paperclip-beads-gastown-bridge

Self-contained no-fork bridge service for Paperclip, Beads, and Gastown.

## Stack
- Python 3.11+
- Typer CLI
- sqlite3 (stdlib)
- pytest

## What is production-ready now
- Real adapter wiring through config/env (`mode=real`)
- Scheduler/worker daemon loop with configurable intervals
- Structured JSON logging + metrics counters flushed to JSON file
- Alert hooks for outbox failures and DLQ threshold (stdout + optional webhook)
- Operational CLI: `run-daemon`, `backfill-reconcile`, `outbox-drain`, `doctor`/`check`
- Config validation with schema + sample config
- Graceful shutdown on SIGINT/SIGTERM

## Project layout
- `bridge_spec_v1.md` - full integration specification
- `bridge/` - implementation
- `bridge/adapters/` - Paperclip API, Beads CLI, Gastown CLI interfaces
- `bridge/migrations/` - SQLite migrations
- `tests/` - contract + behavior + e2e simulation tests
- `config.sample.json` - single-node deployment config template
- `config.schema.json` - JSON schema for config

## Setup
```bash
cd /Users/tarun-agentic/.openclaw/workspace/downloads/paperclip-beads-gastown-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Configuration
1) Copy sample config and edit values:
```bash
cp config.sample.json config.json
```
2) Optionally override via env vars:
- `BRIDGE_MODE`, `BRIDGE_DB_PATH`, `BRIDGE_WORKER_ID`
- `PAPERCLIP_BASE_URL`, `PAPERCLIP_TOKEN`
- `BEADS_BIN`, `GASTOWN_BIN`
- `BRIDGE_METRICS_FILE`, `BRIDGE_ALERT_WEBHOOK`, `BRIDGE_DLQ_WARN_THRESHOLD`
- interval overrides: `BRIDGE_PHASE1_SECONDS`, `BRIDGE_PHASE2_SECONDS`, `BRIDGE_PHASE3_SECONDS`, `BRIDGE_OUTBOX_DRAIN_SECONDS`, `BRIDGE_LOOP_SLEEP_SECONDS`

## Real usage command order (single node)
```bash
# 1) one-time DB migrate
bridge migrate --db-path ./state/bridge.db

# 2) verify connectivity/health before starting service
bridge doctor --config config.json

# 3) start daemon (steady-state operation)
bridge run-daemon --config config.json

# 4) on demand operations
bridge outbox-drain --config config.json
bridge backfill-reconcile --config config.json --iterations 5
```

## Operations runbook
- **Health check**: run `bridge check --config config.json` (same as doctor, non-zero exit on failure).
- **Metrics**: inspect configured metrics JSON file (default `bridge.metrics.json`).
- **Logs**: daemon prints structured JSON logs to stdout.
- **DLQ triage**:
  1. Run `bridge outbox-drain --config config.json`.
  2. Inspect alerts/logs for failing event ids.
  3. Fix remote cause (auth/availability/mapping).
  4. Retry processing with `outbox-drain`.
- **Graceful stop**: send SIGINT/SIGTERM; daemon exits cleanly after current loop.
- **Recovery**: restart daemon; pending outbox + lease logic resumes safely.

## Test
```bash
.venv/bin/pytest -q
```
