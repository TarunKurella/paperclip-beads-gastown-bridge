# paperclip-beads-gastown-bridge

<p align="left">
  <a href="https://github.com/TarunKurella/paperclip-beads-gastown-bridge/actions/workflows/ci.yml">
    <img alt="CI" src="https://github.com/TarunKurella/paperclip-beads-gastown-bridge/actions/workflows/ci.yml/badge.svg" />
  </a>
  <img alt="python" src="https://img.shields.io/badge/python-3.11%2B-blue" />
  <img alt="cli" src="https://img.shields.io/badge/CLI-Typer-7A4CE0" />
  <img alt="mode" src="https://img.shields.io/badge/runtime-mock%20%7C%20real-0A7EA4" />
  <img alt="storage" src="https://img.shields.io/badge/state-sqlite-lightgrey" />
  <img alt="license" src="https://img.shields.io/badge/license-MIT-green" />
</p>

A no-fork operations bridge that keeps **Paperclip**, **Beads**, and **Gastown** in sync — designed for both:

- **humans** running it interactively in terminal
- **agents/automation** running it non-interactively in CI/containers

---

## Why this exists

Teams often use different systems for planning, execution, and coordination. This bridge gives you one operational loop:

1. **Visibility sync** (status alignment)
2. **Assignment automation** (hook attachment flow)
3. **Reconcile** (corrects drift)
4. **Reliable outbox + retries + DLQ** (safe delivery pattern)

The goal: fewer manual handoffs, fewer mismatches, more predictable execution.

> Safety default: **single-writer mode ON** (`status_authority=paperclip`) to prevent ping-pong races.

### Sync trigger strategy

- Primary trigger is **polling** via daemon intervals (`phase1/phase2/phase3/outbox`).
- Manual triggers are available via CLI commands.
- No inbound webhook trigger yet (planned enhancement).

---

## What it does

- Real adapter wiring via config/env (`mode=real`)
- Phase-based orchestration + daemon loop
- Structured JSON logs
- Metrics counters persisted to JSON
- Outbox with retry/backoff and DLQ
- Health checks (`doctor`, `check`)
- UX-first commands for onboarding and operations (`preflight`, `onboard`, `walkthrough`, `start`, `tui`)

---

## Architecture (high-level)

```text
Paperclip API ---> phase1/status map ---->
                                      Beads CLI
Paperclip assignee -> phase2/id map -----> Gastown hook attach

phase3 reconcile closes drift between Paperclip and Beads

All writes go through outbox_events (retry/backoff/DLQ)
```

---

## Install

```bash
cd /Users/tarun-agentic/.openclaw/workspace/downloads/paperclip-beads-gastown-bridge
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

---

## Quickstart

## Human / interactive

```bash
bridge preflight
bridge onboard
bridge walkthrough
bridge start
```

- `preflight`: checks OS dependencies and prints exact install hints (RHEL-ready hints included)
- `onboard`: interactive wizard to generate real config
- `walkthrough`: safe dummy flow so you learn behavior before touching production
- `start`: health + one sync pass + live TUI

## Agent / non-interactive

```bash
bridge preflight --json
bridge onboard --yes --out config.real.local.json
bridge start --agent --quiet-json --config config.real.local.json
```

- outputs machine-friendly JSON
- no TUI, no prompt

---

## Command guide

### Setup / UX

- `bridge preflight` — OS-aware dependency checks + fix hints
- `bridge onboard` — onboarding wizard for real config
- `bridge walkthrough` — dummy end-to-end tutorial
- `bridge plugin-init` — scaffold external Paperclip plugin integration (no upstream source edits)
- `bridge tui` — live terminal dashboard
- `bridge start` — one-command startup

### Core operations

- `bridge check --config <file>` — health gate (non-zero on failure)
- `bridge phase1-sync --config <file>`
- `bridge phase2-assign --config <file>`
- `bridge phase3-reconcile --config <file>`
- `bridge outbox-drain --config <file>`
- `bridge backfill-reconcile --config <file> --iterations 5`
- `bridge run-daemon --config <file>`

### Data/bootstrap

- `bridge migrate --db-path ./state/bridge.db`

### Paperclip plugin integration (without touching Paperclip source)

```bash
bridge plugin-init --output-dir ./integrations/plugin-bridge-ops --package-name @acme/plugin-bridge-ops
```

This creates a standalone plugin scaffold that calls bridge CLI for:
- status snapshot (`bridge status --json`)
- outbox drain action (`bridge outbox-drain`)

Install the built plugin in Paperclip via local-path plugin install API.

---

## Real-mode prerequisites

- Paperclip API reachable (example: `http://localhost:3100`)
- Beads CLI available (`bd`)
- Gastown CLI available (`gt`)
- Dolt available for Beads/Gastown runtime
- tmux recommended for full GT runtime behavior

Use `bridge preflight` to verify quickly.

---

## Configuration

Use JSON config file (`--config`) + optional env overrides.

Key fields:

- `mode`: `mock` or `real`
- `db_path`
- `worker_id`
- `paperclip_base_url`
- `paperclip_token` (optional)
- `beads_bin`, `gastown_bin`
- `single_writer` (default `true`)
- `status_authority` (default `paperclip`)
- `paperclip_company_id` (recommended for multi-company isolation)
- `paperclip_project_id` (reserved for project-level routing)
- `intervals.*`
- `alerts.dlq_warn_threshold`
- `metrics.file_path`

You can bootstrap a ready real config with:

```bash
bridge onboard --yes --out config.real.local.json
```

---

## Production runbook

1. **Preflight**
   ```bash
   bridge preflight
   ```
2. **Health gate**
   ```bash
   bridge check --config config.real.local.json
   ```
3. **Run daemon**
   ```bash
   bridge run-daemon --config config.real.local.json
   ```
4. **If backlog accumulates**
   ```bash
   bridge outbox-drain --config config.real.local.json
   bridge backfill-reconcile --config config.real.local.json --iterations 5
   ```

---

## Troubleshooting

### `check` fails
- run `bridge preflight`
- verify Paperclip URL in config
- verify `bd` / `gt` binaries in PATH

### DLQ increases
- inspect failing event IDs from logs
- fix upstream cause (mapping/auth/workspace context)
- rerun `outbox-drain`

### Agent output noisy in automation
- use `bridge start --agent --quiet-json` for single JSON summary

---

## Testing

```bash
.venv/bin/pytest -q
```

Current baseline: **25 passing tests**.

---

## Repo layout

- `bridge/` — app code
- `bridge/adapters/` — external interfaces
- `bridge/migrations/` — sqlite schema
- `tests/` — behavior and integration-safe tests
- `config.sample.json` / `config.schema.json`

---

## Motivation in one line

**Make multi-system execution feel like one coherent control plane — from terminal, for humans and agents.**
