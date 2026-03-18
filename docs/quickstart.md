# Quickstart

## Human flow

```bash
bridge preflight
bridge onboard
bridge walkthrough
bridge start
```

## Agent flow

```bash
bridge preflight --json
bridge onboard --yes --out config.real.local.json
bridge start --agent --quiet-json --config config.real.local.json
```

## Core ops

```bash
bridge check --config config.real.local.json
bridge run-daemon --config config.real.local.json
bridge outbox-drain --config config.real.local.json
bridge dlq-replay --config config.real.local.json
bridge status --config config.real.local.json --json
bridge guardrail-check --config config.real.local.json --paperclip-id <id> --json
bridge exec-plan --config config.real.local.json --json
bridge blockers-push --config config.real.local.json
```
