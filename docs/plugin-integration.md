# Paperclip Plugin Integration (No Upstream Edits)

This project intentionally avoids editing Paperclip/Beads/Gastown source code.

Use scaffold:

```bash
bridge plugin-init \
  --output-dir ./integrations/plugin-bridge-ops \
  --package-name @acme/plugin-bridge-ops \
  --with-ci
```

Runtime contract:

- Plugin worker is npm/TS
- Bridge engine is Python CLI
- Configure plugin worker environment:
  - `BRIDGE_BIN` (default: `bridge`)
  - `BRIDGE_CONFIG_PATH` (bridge config file)

Install local plugin into Paperclip:

```bash
curl -X POST http://127.0.0.1:3100/api/plugins/install \
  -H "Content-Type: application/json" \
  -d '{"packageName":"/absolute/path/to/plugin-bridge-ops","isLocalPath":true}'
```
