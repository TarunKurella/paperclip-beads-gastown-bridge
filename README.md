# paperclip-beads-gastown-bridge

Self-contained no-fork bridge service for Paperclip, Beads, and Gastown.

## Stack
- Python 3.11+
- Typer CLI
- sqlite3 (stdlib)
- pytest

## Project layout
- `bridge_spec_v1.md` - full integration specification
- `bridge/` - implementation
- `bridge/adapters/` - Paperclip API, Beads CLI, Gastown CLI interfaces
- `bridge/migrations/` - SQLite migrations
- `tests/` - contract + behavior + e2e simulation tests

## Setup
```bash
cd /Users/tarun-agentic/.openclaw/workspace/downloads/paperclip-beads-gastown-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Run
```bash
bridge migrate --db-path bridge.db
bridge phase1-sync --db-path bridge.db
bridge phase2-assign --db-path bridge.db
bridge phase3-reconcile --db-path bridge.db --worker-id worker-1
```

## Test
```bash
pytest -q
```

## Spec-build-test-repeat workflow
1. Update `bridge_spec_v1.md` first.
2. Implement/adjust bridge behavior in `bridge/`.
3. Add/update fixtures and tests in `tests/`.
4. Run `pytest -q`.
5. Commit only when spec + code + tests align.

## Notes
- No upstream repository modifications required.
- Outbox + dedupe + lease + DLQ + reconciliation primitives are built in.
