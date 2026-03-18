# paperclip-beads-gastown-bridge

<p>
  <a href="https://github.com/TarunKurella/paperclip-beads-gastown-bridge/actions/workflows/ci.yml">
    <img alt="CI" src="https://github.com/TarunKurella/paperclip-beads-gastown-bridge/actions/workflows/ci.yml/badge.svg" />
  </a>
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-blue" />
  <img alt="Runtime" src="https://img.shields.io/badge/runtime-mock%20%7C%20real-0ea5e9" />
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green" />
</p>

**A safe sync control plane for Paperclip + Beads + Gastown.**

- Human-friendly terminal UX
- Agent-friendly JSON mode
- Race-safe default (`single_writer=true`)
- Optional Paperclip plugin integration (without editing upstream repos)

---

## Why try this?

If your team coordinates work across Paperclip, Beads, and Gastown, this gives you one practical runtime for:

- status synchronization
- assignment to hook automation
- drift reconciliation
- reliable delivery via outbox + retries + DLQ

No fragile glue scripts. No source edits in the three upstream systems.

---

## Architecture

![Bridge architecture](docs/architecture.svg)

---

## 60-second quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

bridge preflight
bridge onboard
bridge walkthrough
bridge start
```

---

## Human vs Agent flows

### Human / interactive

```bash
bridge preflight
bridge onboard
bridge walkthrough
bridge start
```

### Agent / non-interactive

```bash
bridge preflight --json
bridge onboard --yes --out config.real.local.json
bridge start --agent --quiet-json --config config.real.local.json
```

---

## Safety defaults (important)

- `single_writer = true`
- `status_authority = "paperclip"`

This prevents ping-pong writes and race loops when multiple automation systems coexist.

---

## Plugin integration (optional)

Scaffold a standalone Paperclip plugin wrapper:

```bash
bridge plugin-init \
  --output-dir ./integrations/plugin-bridge-ops \
  --package-name @acme/plugin-bridge-ops \
  --with-ci
```

This generates an npm/TS plugin that calls the Python `bridge` CLI.

---

## Commands you’ll actually use

```bash
bridge check --config config.real.local.json
bridge status --config config.real.local.json --json
bridge run-daemon --config config.real.local.json
bridge outbox-drain --config config.real.local.json
bridge dlq-replay --config config.real.local.json
bridge map-add --config config.real.local.json --paperclip-id <id> --beads-id <id>
bridge owner-set --config config.real.local.json --paperclip-id <id> --owner beads_runner
bridge phase-feedback --config config.real.local.json
```

---

## Multi-company support

Use company-scoped configs (recommended one worker per company), with:

- `paperclip_company_id`
- scoped mappings (`id_map_scoped`)
- scoped dedupe keys

---

## Docs

- [Quickstart](docs/quickstart.md)
- [Plugin integration](docs/plugin-integration.md)
- [Architecture diagram (SVG)](docs/architecture.svg)

---

## License

MIT
