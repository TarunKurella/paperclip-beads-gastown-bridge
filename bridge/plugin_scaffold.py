from __future__ import annotations

from pathlib import Path

PACKAGE_JSON = """{
  \"name\": \"__PACKAGE_NAME__\",
  \"version\": \"0.1.0\",
  \"private\": true,
  \"type\": \"module\",
  \"scripts\": {
    \"build\": \"echo 'Use your Paperclip plugin toolchain to build this plugin'\",
    \"typecheck\": \"echo 'add tsconfig + tsc if needed'\"
  },
  \"dependencies\": {
    \"@paperclipai/plugin-sdk\": \"*\"
  }
}
"""

MANIFEST_TS = """import type { PaperclipPluginManifestV1 } from \"@paperclipai/plugin-sdk\";

const manifest: PaperclipPluginManifestV1 = {
  id: \"__PLUGIN_ID__\",
  apiVersion: 1,
  version: \"0.1.0\",
  displayName: \"Bridge Ops\",
  description: \"Operate paperclip-beads-gastown-bridge from Paperclip UI\",
  author: \"Bridge Team\",
  categories: [\"operations\"],
  capabilities: [\"ui.dashboardWidget.register\", \"actions.register\", \"data.register\"],
  entrypoints: {
    worker: \"./dist/worker.js\",
    ui: \"./dist/ui\"
  },
  ui: {
    slots: [
      {
        type: \"dashboardWidget\",
        id: \"bridge-ops-widget\",
        displayName: \"Bridge Ops\",
        exportName: \"BridgeOpsWidget\"
      }
    ]
  }
};

export default manifest;
"""

WORKER_TS = """import { spawn } from \"node:child_process\";
import { definePlugin, runWorker, type PaperclipPlugin } from \"@paperclipai/plugin-sdk\";

const BRIDGE_CONFIG = process.env.BRIDGE_CONFIG_PATH ?? \"config.real.local.json\";

function runBridge(args: string[]): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(\"bridge\", args, { stdio: [\"ignore\", \"pipe\", \"pipe\"] });
    let stdout = \"\";
    let stderr = \"\";
    child.stdout.on(\"data\", (d) => (stdout += String(d)));
    child.stderr.on(\"data\", (d) => (stderr += String(d)));
    child.on(\"error\", reject);
    child.on(\"close\", (code) => resolve({ code, stdout: stdout.trim(), stderr: stderr.trim() }));
  });
}

const plugin: PaperclipPlugin = definePlugin({
  async setup(ctx) {
    ctx.data.register(\"bridge-status\", async () => {
      const res = await runBridge([\"status\", \"--config\", BRIDGE_CONFIG, \"--json\"]);
      if (res.code !== 0) return { ok: false, error: res.stderr || res.stdout };
      try {
        return { ok: true, data: JSON.parse(res.stdout) };
      } catch {
        return { ok: false, error: \"invalid JSON from bridge status\", raw: res.stdout };
      }
    });

    ctx.actions.register(\"bridge-outbox-drain\", async () => {
      const res = await runBridge([\"outbox-drain\", \"--config\", BRIDGE_CONFIG]);
      return { ok: res.code === 0, stdout: res.stdout, stderr: res.stderr };
    });
  }
});

export default plugin;
runWorker(plugin, import.meta.url);
"""

UI_TSX = """import { usePluginAction, usePluginData } from \"@paperclipai/plugin-sdk/ui\";

export function BridgeOpsWidget() {
  const status = usePluginData<{ ok: boolean; data?: any; error?: string }>(\"bridge-status\", {});
  const drain = usePluginAction(\"bridge-outbox-drain\");

  const snap = status.data?.data;

  return (
    <section aria-label=\"Bridge Ops Widget\">
      <strong>Bridge Ops</strong>
      {status.loading ? <div>Loading…</div> : null}
      {status.error ? <div>Error: {String(status.error)}</div> : null}
      {status.data?.ok === false ? <div>Bridge error: {status.data?.error}</div> : null}
      {snap ? (
        <ul>
          <li>health: {snap.health}</li>
          <li>pending: {snap.outbox?.pending}</li>
          <li>sent: {snap.outbox?.sent}</li>
          <li>dlq: {snap.outbox?.dlq}</li>
        </ul>
      ) : null}
      <button onClick={() => drain.mutate({})} disabled={drain.loading}>
        Drain outbox
      </button>
      {drain.data ? <pre>{JSON.stringify(drain.data, null, 2)}</pre> : null}
    </section>
  );
}
"""

README = """# Bridge Ops Plugin (external)

This is a standalone Paperclip plugin scaffold that integrates with `paperclip-beads-gastown-bridge` CLI.

## Why this exists

- Does **not** require changing Paperclip/Beads/Gastown source code.
- Uses plugin APIs to display bridge health and trigger safe operations.

## What it does

- `bridge-status` data endpoint -> calls `bridge status --json`
- `bridge-outbox-drain` action -> calls `bridge outbox-drain`
- dashboard widget shows current queue/health

## Setup

1. Ensure `bridge` CLI is in PATH where Paperclip plugin worker runs.
2. Optionally set `BRIDGE_CONFIG_PATH` env var.
3. Build this plugin with your Paperclip plugin toolchain.
4. Install in Paperclip as local path:

```bash
curl -X POST http://127.0.0.1:3100/api/plugins/install \
  -H \"Content-Type: application/json\" \
  -d '{"packageName":"/absolute/path/to/plugin-bridge-ops", "isLocalPath":true}'
```

## Note

This scaffold is intentionally minimal and safe. Expand actions only if needed.
"""


def create_plugin_scaffold(output_dir: str, package_name: str = "@acme/plugin-bridge-ops") -> Path:
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    plugin_id = package_name.replace("@", "").replace("/", ".")

    (out / "src").mkdir(exist_ok=True)
    (out / "src" / "ui").mkdir(parents=True, exist_ok=True)

    (out / "package.json").write_text(PACKAGE_JSON.replace("__PACKAGE_NAME__", package_name))
    (out / "README.md").write_text(README)
    (out / "src" / "manifest.ts").write_text(MANIFEST_TS.replace("__PLUGIN_ID__", plugin_id))
    (out / "src" / "worker.ts").write_text(WORKER_TS)
    (out / "src" / "ui" / "index.tsx").write_text(UI_TSX)
    (out / "src" / "index.ts").write_text('export { default as manifest } from "./manifest";\n')

    return out
