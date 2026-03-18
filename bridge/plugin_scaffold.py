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

const BRIDGE_BIN = process.env.BRIDGE_BIN ?? \"bridge\";
const BRIDGE_CONFIG = process.env.BRIDGE_CONFIG_PATH ?? \"config.real.local.json\";

function runBridge(args: string[]): Promise<{ code: number | null; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(BRIDGE_BIN, args, { stdio: [\"ignore\", \"pipe\", \"pipe\"] });
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

    ctx.actions.register(\"bridge-safe-cycle\", async () => {
      const res = await runBridge([\"start\", \"--agent\", \"--quiet-json\", \"--skip-tui\", \"--config\", BRIDGE_CONFIG]);
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(res.stdout);
      } catch {
        parsed = { raw: res.stdout };
      }
      return { ok: res.code === 0, result: parsed, stderr: res.stderr };
    });

    ctx.actions.register(\"bridge-guardrail-check\", async (params) => {
      const paperclipId = String((params as { paperclipId?: string }).paperclipId ?? \"\").trim();
      if (!paperclipId) return { ok: false, error: \"paperclipId is required\" };
      const res = await runBridge([\"guardrail-check\", \"--json\", \"--config\", BRIDGE_CONFIG, \"--paperclip-id\", paperclipId]);
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(res.stdout);
      } catch {
        parsed = { raw: res.stdout };
      }
      return { ok: res.code === 0, result: parsed, stderr: res.stderr };
    });

    ctx.actions.register(\"bridge-exec-plan\", async () => {
      const res = await runBridge([\"exec-plan\", \"--json\", \"--config\", BRIDGE_CONFIG]);
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(res.stdout);
      } catch {
        parsed = { raw: res.stdout };
      }
      return { ok: res.code === 0, result: parsed, stderr: res.stderr };
    });

    ctx.actions.register(\"bridge-blockers-push\", async () => {
      const res = await runBridge([\"blockers-push\", \"--config\", BRIDGE_CONFIG]);
      return { ok: res.code === 0, stdout: res.stdout, stderr: res.stderr };
    });
  }
});

export default plugin;
runWorker(plugin, import.meta.url);
"""

UI_TSX = """import { useMemo, useState } from "react";
import { usePluginAction, usePluginData } from "@paperclipai/plugin-sdk/ui";

const box: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  borderRadius: 10,
  padding: 10,
  background: "#fff",
};

const kpi: React.CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(3, minmax(70px, 1fr))",
  gap: 8,
};

export function BridgeOpsWidget() {
  const status = usePluginData<{ ok: boolean; data?: any; error?: string }>("bridge-status", {});
  const drain = usePluginAction("bridge-outbox-drain");
  const safeCycle = usePluginAction("bridge-safe-cycle");
  const guardrail = usePluginAction("bridge-guardrail-check");
  const execPlan = usePluginAction("bridge-exec-plan");
  const blockersPush = usePluginAction("bridge-blockers-push");
  const [paperclipId, setPaperclipId] = useState("");

  const snap = status.data?.data;
  const cycle = safeCycle.data?.result;
  const gate = guardrail.data?.result;
  const plan = (execPlan.data?.result ?? []) as Array<{ beads_id: string; paperclip_id?: string; status?: string; title?: string }>;

  const healthColor = useMemo(() => (snap?.health === "ok" ? "#16a34a" : "#d97706"), [snap?.health]);

  return (
    <section aria-label="Bridge Ops Widget" style={{ display: "grid", gap: 10, fontSize: 13 }}>
      <div style={{ ...box, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <strong>Bridge Ops</strong>
        <span style={{ color: healthColor, fontWeight: 700 }}>{String(snap?.health ?? "unknown").toUpperCase()}</span>
      </div>

      {status.loading ? <div style={box}>Loading status…</div> : null}
      {status.error ? <div style={box}>Error: {String(status.error)}</div> : null}
      {status.data?.ok === false ? <div style={box}>Bridge error: {status.data?.error}</div> : null}

      {snap ? (
        <div style={box}>
          <div style={kpi}>
            <div><strong>{snap.outbox?.pending}</strong><div>pending</div></div>
            <div><strong>{snap.outbox?.sent}</strong><div>sent</div></div>
            <div><strong>{snap.outbox?.dlq}</strong><div>dlq</div></div>
          </div>
          <div style={{ marginTop: 8, color: "#475569" }}>
            authority={snap.status_authority} · single_writer={String(snap.single_writer)}
          </div>
        </div>
      ) : null}

      <div style={{ ...box, display: "grid", gap: 8 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => safeCycle.mutate({})} disabled={safeCycle.loading}>Safe run cycle</button>
          <button onClick={() => drain.mutate({})} disabled={drain.loading}>Drain outbox</button>
          <button onClick={() => execPlan.mutate({})} disabled={execPlan.loading}>Refresh exec plan</button>
          <button onClick={() => blockersPush.mutate({})} disabled={blockersPush.loading}>Push blockers</button>
        </div>

        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={paperclipId}
            onChange={(e) => setPaperclipId(e.target.value)}
            placeholder="paperclip issue id"
            style={{ flex: 1 }}
          />
          <button onClick={() => guardrail.mutate({ paperclipId })} disabled={guardrail.loading || !paperclipId}>
            Guardrail check
          </button>
        </div>
      </div>

      {gate ? (
        <div style={box}>
          <strong>Guardrail</strong>
          <div>allowed={String(gate.allowed)} · reason={String(gate.reason)} · owner={String(gate.owner)}</div>
          {gate.beads_id ? <div>beads_id={String(gate.beads_id)}</div> : null}
        </div>
      ) : null}

      {cycle ? (
        <div style={box}>
          <strong>Cycle result</strong>
          <div>
            queued={cycle.phase2_assignments} · skipped_owner={cycle.phase2_skipped_owner} ·
            skipped_unmapped={cycle.phase2_skipped_unmapped} · skipped_lock={cycle.phase2_skipped_lock}
          </div>
        </div>
      ) : null}

      <div style={box}>
        <strong>DAG exec plan ({plan.length})</strong>
        {plan.length === 0 ? <div style={{ color: "#64748b" }}>No ready tasks right now</div> : null}
        {plan.slice(0, 8).map((row) => (
          <div key={row.beads_id} style={{ marginTop: 6 }}>
            <code>{row.beads_id}</code> → <code>{row.paperclip_id ?? "(unmapped)"}</code> · {row.status} · {row.title}
          </div>
        ))}
      </div>

      {safeCycle.data ? <pre style={box}>{JSON.stringify(safeCycle.data, null, 2)}</pre> : null}
      {drain.data ? <pre style={box}>{JSON.stringify(drain.data, null, 2)}</pre> : null}
      {blockersPush.data ? <pre style={box}>{JSON.stringify(blockersPush.data, null, 2)}</pre> : null}
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
- `bridge-safe-cycle` action -> calls `bridge start --agent --quiet-json --skip-tui`
- `bridge-guardrail-check` action -> calls `bridge guardrail-check --json`
- dashboard widget shows queue/health + skip reasons + guardrail result

## Setup

1. Install bridge CLI in plugin runtime env (recommended):
   - `pip install paperclip-beads-gastown-bridge` (or install from source)
2. Ensure `bridge` is in PATH, or set `BRIDGE_BIN` to absolute binary path.
3. Optionally set `BRIDGE_CONFIG_PATH` env var.
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

CI_YML = """name: Plugin CI

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: corepack enable
      - run: pnpm install
      - run: pnpm run typecheck || true
      - run: pnpm run build || true
"""

TSCONFIG_JSON = """{
  \"compilerOptions\": {
    \"target\": \"ES2022\",
    \"module\": \"ESNext\",
    \"moduleResolution\": \"Bundler\",
    \"jsx\": \"react-jsx\",
    \"strict\": true,
    \"skipLibCheck\": true,
    \"noEmit\": true
  },
  \"include\": [\"src/**/*\"]
}
"""


def create_plugin_scaffold(output_dir: str, package_name: str = "@acme/plugin-bridge-ops", with_ci: bool = False) -> Path:
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

    if with_ci:
        (out / "tsconfig.json").write_text(TSCONFIG_JSON)
        gh = out / ".github" / "workflows"
        gh.mkdir(parents=True, exist_ok=True)
        (gh / "plugin-ci.yml").write_text(CI_YML)

    return out
