# Paperclip Plugin Integration (Step-by-step)

This integration keeps upstream repos untouched. The plugin is npm/TS; bridge runtime is Python CLI.

## 1) Ensure bridge CLI exists where Paperclip runs

```bash
# from bridge repo
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

# verify
bridge --help
```

If `bridge` is not globally available, set `BRIDGE_BIN` later to absolute path, e.g.:

```bash
export BRIDGE_BIN=/absolute/path/to/bridge
```

## 2) Prepare bridge runtime config

```bash
bridge preflight
bridge onboard --yes --out config.real.local.json
bridge check --config config.real.local.json
```

(Optional but recommended for execution control)

```bash
# allow selected task to run from beads side
bridge owner-set --config config.real.local.json --paperclip-id <paperclip_uuid> --owner beads_runner
```

## 3) Scaffold plugin package

```bash
bridge plugin-init \
  --output-dir ./integrations/plugin-bridge-ops \
  --package-name @acme/plugin-bridge-ops \
  --with-ci
```

## 4) Build plugin (inside Paperclip repo/toolchain)

Use your standard Paperclip plugin build workflow for the scaffolded package.

## 5) Set plugin worker env vars

In the environment where Paperclip plugin worker runs:

```bash
export BRIDGE_CONFIG_PATH=/absolute/path/to/paperclip-beads-gastown-bridge/config.real.local.json
# optional if bridge not in PATH
export BRIDGE_BIN=/absolute/path/to/bridge
```

## 6) Install plugin into Paperclip

```bash
curl -X POST http://127.0.0.1:3100/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"packageName":"/absolute/path/to/integrations/plugin-bridge-ops","isLocalPath":true}'
```

## 7) Verify in Paperclip UI

Widget should show:
- health
- outbox counts
- status authority + single-writer
- buttons: **Safe run cycle**, **Drain outbox**

## 8) Verify no double-runs

- Keep default: `single_writer=true`, `status_authority=paperclip`
- Use ownership rules only where needed:

```bash
# allow Beads-side execution only for selected tasks
bridge owner-set --config config.real.local.json --paperclip-id <paperclip_uuid> --owner beads_runner

# inspect ownership rules
bridge owner-list --config config.real.local.json --json

# check one task before running
bridge guardrail-check --config config.real.local.json --paperclip-id <paperclip_uuid> --json

# global status
bridge status --config config.real.local.json --json
```

`bridge-safe-cycle` result should include skip counters:
- `phase2_skipped_owner`
- `phase2_skipped_unmapped`
- `phase2_skipped_lock`

These counters are expected safeguards, not failures.

## 9) Optional bounded feedback from Beads -> Paperclip

```bash
bridge phase-feedback --config config.real.local.json
```

This only sends execution-signal statuses (in_progress/blocked/done) for tasks owned by `beads_runner`. It is intentionally limited to prevent race loops.
