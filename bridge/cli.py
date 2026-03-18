from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import termios
import time
import tty
import urllib.error
import urllib.request
from pathlib import Path

import typer

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.config import AlertConfig, ConfigError, MetricsConfig, RuntimeConfig, load_config
from bridge.daemon import run_daemon
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.plugin_scaffold import create_plugin_scaffold
from bridge.preflight import run_preflight
from bridge.runtime import build_service
from bridge.service import BridgeService
from bridge.ux import (
    dashboard_snapshot,
    detect_bin,
    detect_paperclip_base_url,
    load_onboarding_state,
    save_onboarding_state,
    write_runtime_config,
)

app = typer.Typer(
    help=(
        "Paperclip/Beads/Gastown bridge\n\n"
        "Human-friendly flow:\n"
        "  bridge preflight          # OS checks + install hints\n"
        "  bridge onboard            # interactive setup wizard\n"
        "  bridge walkthrough        # dummy guided example\n"
        "  bridge start              # guided start + optional TUI\n\n"
        "Agent/non-interactive flow:\n"
        "  bridge preflight --json\n"
        "  bridge onboard --yes --out config.real.local.json\n"
        "  bridge start --agent --config config.real.local.json"
    )
)


def _load(config_path: str | None):
    try:
        return load_config(config_path)
    except ConfigError as exc:
        raise typer.BadParameter(str(exc)) from exc


@app.command()
def migrate(
    db_path: str = typer.Option("bridge.db", help="SQLite file path"),
) -> None:
    conn = db.connect(db_path)
    db.migrate(conn, str(Path(__file__).parent / "migrations"))
    typer.echo("migrations applied")


@app.command("phase1-sync")
def phase1_sync(config: str | None = typer.Option(None, "--config", help="JSON config file path")) -> None:
    cfg = _load(config)
    svc, logger, metrics, _alerts = build_service(cfg)
    svc.phase1_visibility_sync()
    sent = svc.process_outbox()
    metrics.inc("phase1_runs")
    metrics.inc("outbox_sent", sent)
    metrics.flush()
    logger.info("phase1_complete", sent=sent)
    typer.echo(f"phase1 complete: sent={sent}")


@app.command("phase2-assign")
def phase2_assign(config: str | None = typer.Option(None, "--config", help="JSON config file path")) -> None:
    cfg = _load(config)
    svc, logger, metrics, _alerts = build_service(cfg)
    result = svc.phase2_assignment_automation()
    sent = svc.process_outbox()
    metrics.inc("phase2_runs")
    metrics.inc("outbox_sent", sent)
    metrics.flush()
    logger.info(
        "phase2_complete",
        sent=sent,
        queued=result.assignments_attached,
        skipped_owner=result.skipped_owner,
        skipped_unmapped=result.skipped_unmapped,
        skipped_lock=result.skipped_lock,
    )
    typer.echo(
        f"phase2 complete: sent={sent} queued={result.assignments_attached} "
        f"skipped_owner={result.skipped_owner} skipped_unmapped={result.skipped_unmapped} skipped_lock={result.skipped_lock}"
    )


@app.command("phase3-reconcile")
def phase3_reconcile(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    worker_id: str | None = typer.Option(None, help="Override worker id"),
) -> None:
    cfg = _load(config)
    if worker_id:
        cfg.worker_id = worker_id
    svc, logger, metrics, _alerts = build_service(cfg)
    result = svc.phase3_reconcile()
    metrics.inc("phase3_runs")
    metrics.inc("phase3_reconciled", result.reconciled)
    metrics.flush()
    logger.info("phase3_complete", reconciled=result.reconciled)
    typer.echo(f"phase3 complete: reconciled={result.reconciled}")


@app.command("outbox-drain")
def outbox_drain(config: str | None = typer.Option(None, "--config", help="JSON config file path")) -> None:
    cfg = _load(config)
    svc, logger, metrics, alerts = build_service(cfg)

    def _on_failure(row, exc: Exception) -> None:
        alerts.send("warning", "outbox event failed", event_id=row["event_id"], error=str(exc))

    sent = svc.process_outbox(on_failure=_on_failure)
    dlq_count = db.count_outbox_by_status(svc.conn, "dlq")
    metrics.inc("outbox_drains")
    metrics.inc("outbox_sent", sent)
    metrics.set("outbox_dlq", dlq_count)
    metrics.flush()
    logger.info("outbox_drain_complete", sent=sent, dlq_count=dlq_count)
    typer.echo(f"outbox drain complete: sent={sent} dlq={dlq_count}")


@app.command("backfill-reconcile")
def backfill_reconcile(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    iterations: int = typer.Option(3, min=1, help="Number of reconcile passes"),
) -> None:
    cfg = _load(config)
    svc, logger, metrics, _alerts = build_service(cfg)
    total = 0
    for _ in range(iterations):
        result = svc.phase3_reconcile()
        total += result.reconciled
    metrics.inc("backfill_runs")
    metrics.inc("phase3_reconciled", total)
    metrics.flush()
    logger.info("backfill_reconcile_complete", iterations=iterations, reconciled=total)
    typer.echo(f"backfill reconcile complete: iterations={iterations} reconciled={total}")


@app.command("run-daemon")
def run_daemon_cmd(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
) -> None:
    cfg = _load(config)
    svc, logger, metrics, alerts = build_service(cfg)
    run_daemon(svc, cfg, logger, metrics, alerts)


@app.command("doctor")
def doctor(config: str | None = typer.Option(None, "--config", help="JSON config file path")) -> None:
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    checks = {
        "config_mode": cfg.mode,
        "db_ok": False,
        "paperclip_ok": False,
        "beads_ok": False,
        "status": "ok",
    }
    try:
        svc.conn.execute("SELECT 1")
        checks["db_ok"] = True
        svc.adapters.paperclip.list_items()
        checks["paperclip_ok"] = True
        svc.adapters.beads.list_items()
        checks["beads_ok"] = True
    except Exception as exc:
        checks["status"] = "fail"
        checks["error"] = str(exc)

    typer.echo(json.dumps(checks, indent=2, sort_keys=True))
    if checks["status"] != "ok":
        raise typer.Exit(code=1)


@app.command("check")
def check(config: str | None = typer.Option(None, "--config", help="JSON config file path")) -> None:
    doctor(config)


@app.command("preflight")
def preflight(json_output: bool = typer.Option(False, "--json", help="Machine-readable output")) -> None:
    """OS-aware environment checks with install hints (great for RHEL containers)."""
    result = run_preflight()
    if json_output:
        typer.echo(json.dumps(result))
        if not result["ok"]:
            raise typer.Exit(code=1)
        return

    typer.echo("\nPreflight")
    os_info = result["os"]
    typer.echo(f"OS: {os_info.get('name', os_info.get('system'))}")
    for c in result["checks"]:
        mark = "✅" if c["ok"] else "❌"
        typer.echo(f"{mark} {c['name']}: {c['detail']}")
        if not c["ok"] and c.get("fix"):
            typer.echo(f"   fix: {c['fix']}")

    if not result["ok"]:
        raise typer.Exit(code=1)


@app.command("onboard")
def onboard(
    out: str = typer.Option("config.real.local.json", "--out", help="Config file to generate"),
    yes: bool = typer.Option(False, "--yes", help="Non-interactive defaults"),
) -> None:
    """Interactive onboarding wizard for real-mode setup."""
    default_url = detect_paperclip_base_url()
    default_beads = detect_bin("bd", "bd")
    default_gastown = detect_bin("gt", "gt")

    # show preflight hints first (non-blocking in interactive mode)
    pf = run_preflight()
    if not yes:
        typer.echo("\nBridge Onboarding Wizard (real mode)\n")
        if not pf["ok"]:
            typer.echo("Preflight found missing dependencies:")
            for c in pf["checks"]:
                if not c["ok"]:
                    typer.echo(f"- {c['name']}: {c['detail']}")
                    if c.get("fix"):
                        typer.echo(f"  fix: {c['fix']}")
            typer.echo("")

    if yes:
        paperclip_url = default_url
        beads_bin = default_beads
        gastown_bin = default_gastown
        worker_id = "node-1"
        company_id = None
    else:
        paperclip_url = typer.prompt("Paperclip base URL", default=default_url)
        beads_bin = typer.prompt("Beads binary", default=default_beads)
        gastown_bin = typer.prompt("Gastown binary", default=default_gastown)
        worker_id = typer.prompt("Worker ID", default="node-1")
        company_id = typer.prompt("Paperclip company ID (optional, recommended for multi-company)", default="") or None

    cfg = RuntimeConfig(
        mode="real",
        db_path="./state/bridge.db",
        worker_id=worker_id,
        paperclip_base_url=paperclip_url,
        paperclip_company_id=company_id,
        beads_bin=beads_bin,
        gastown_bin=gastown_bin,
        metrics=MetricsConfig(file_path="./state/bridge.metrics.json"),
        alerts=AlertConfig(dlq_warn_threshold=5),
    )
    write_runtime_config(out, cfg)
    save_onboarding_state(out)
    typer.echo(f"\n✅ Wrote {out}")
    typer.echo("Next: bridge check --config " + out)
    typer.echo("Optional: bridge walkthrough")


@app.command("plugin-init")
def plugin_init(
    output_dir: str = typer.Option("./integrations/plugin-bridge-ops", "--output-dir", help="Where to create plugin scaffold"),
    package_name: str = typer.Option("@acme/plugin-bridge-ops", "--package-name", help="NPM package name"),
    with_ci: bool = typer.Option(False, "--with-ci", help="Include plugin tsconfig + GitHub Actions CI scaffold"),
) -> None:
    """Scaffold an external Paperclip plugin that wraps bridge CLI ops.

    This avoids touching Paperclip/Beads/Gastown source code.
    """
    out = create_plugin_scaffold(output_dir=output_dir, package_name=package_name, with_ci=with_ci)
    typer.echo(f"plugin scaffold created at: {out}")
    if with_ci:
        typer.echo("included: tsconfig.json + .github/workflows/plugin-ci.yml")
    typer.echo("next: build with your Paperclip plugin toolchain, then install via /api/plugins/install")


@app.command("plugin-install")
def plugin_install(
    output_dir: str = typer.Option("./integrations/plugin-bridge-ops", "--output-dir", help="Plugin folder path"),
    package_name: str = typer.Option("@acme/plugin-bridge-ops", "--package-name", help="NPM package name"),
    with_ci: bool = typer.Option(True, "--with-ci/--no-with-ci", help="Include plugin CI scaffold"),
    paperclip_base_url: str = typer.Option("http://127.0.0.1:3100", "--paperclip-base-url", help="Paperclip API base URL"),
    bridge_config_path: str = typer.Option("config.real.local.json", "--bridge-config", help="Bridge config path for plugin runtime"),
    bridge_bin: str | None = typer.Option(None, "--bridge-bin", help="Bridge binary path (defaults to PATH lookup)"),
) -> None:
    """Scaffold plugin and install it into Paperclip as local-path package."""
    out = create_plugin_scaffold(output_dir=output_dir, package_name=package_name, with_ci=with_ci)

    resolved_bridge_bin = bridge_bin or (os.getenv("BRIDGE_BIN") or "bridge")
    resolved_bridge_cfg = str(Path(bridge_config_path).resolve())

    payload = {
        "packageName": str(out),
        "isLocalPath": True,
    }

    url = f"{paperclip_base_url.rstrip('/')}/api/plugins/install"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as res:  # nosec B310
            body = res.read().decode("utf-8", "ignore")
            typer.echo(f"plugin installed: {res.status}")
            if body:
                typer.echo(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "ignore")
        typer.echo(f"plugin install failed: {exc.code}")
        if body:
            typer.echo(body)
        if exc.code == 404:
            typer.echo("\nAPI install route unavailable. Trying Paperclip CLI fallback...")
            paperclip_cli = shutil.which("paperclipai") or shutil.which("paperclip")
            if paperclip_cli:
                try:
                    proc = subprocess.run(
                        [paperclip_cli, "plugin", "install", str(out)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    typer.echo("plugin installed via CLI fallback")
                    if proc.stdout.strip():
                        typer.echo(proc.stdout.strip())
                except subprocess.CalledProcessError as cpe:
                    typer.echo("plugin CLI fallback failed")
                    if cpe.stdout:
                        typer.echo(cpe.stdout.strip())
                    if cpe.stderr:
                        typer.echo(cpe.stderr.strip())
                    raise typer.Exit(code=1)
            else:
                typer.echo("No paperclip CLI found (paperclipai/paperclip).")
                typer.echo("Run manually after updating Paperclip:")
                typer.echo(f"paperclipai plugin install {out}")
                raise typer.Exit(code=1)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"plugin install failed: {exc}")
        raise typer.Exit(code=1)

    typer.echo("\nSet runtime env for Paperclip plugin worker:")
    typer.echo(f"export BRIDGE_CONFIG_PATH={resolved_bridge_cfg}")
    typer.echo(f"export BRIDGE_BIN={resolved_bridge_bin}")
    typer.echo("(set these in the process that runs Paperclip)")


@app.command("walkthrough")
def walkthrough() -> None:
    """Create and run a dummy example flow to teach the real pipeline."""
    typer.echo("\n🧪 Walkthrough: dummy example project")
    conn = db.connect("./state/walkthrough.db")
    db.migrate(conn, str(Path(__file__).parent / "migrations"))

    paperclip = InMemoryPaperclip(
        {
            "pc-1": WorkItem(id="pc-1", status="in_progress", assignee="alice", raw={"title": "Launch plan"}),
            "pc-2": WorkItem(id="pc-2", status="todo", assignee=None, raw={"title": "Budget review"}),
        }
    )
    beads = InMemoryBeads(
        {
            "bead-1": WorkItem(id="bead-1", status="open", raw={"title": "Launch plan"}),
            "bead-2": WorkItem(id="bead-2", status="open", raw={"title": "Budget review"}),
        }
    )
    gastown = InMemoryGastown()
    svc = BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=gastown), worker_id="walkthrough")

    svc.phase1_visibility_sync()
    sent1 = svc.process_outbox()
    phase2 = svc.phase2_assignment_automation()
    sent2 = svc.process_outbox()
    rec = svc.phase3_reconcile()

    typer.echo("Step results:")
    typer.echo(f"- phase1 outbox sent: {sent1}")
    typer.echo(f"- phase2 assignments queued: {phase2.assignments_attached}")
    typer.echo(f"- phase2 outbox sent: {sent2}")
    typer.echo(f"- phase3 reconciled: {rec.reconciled}")
    typer.echo(f"- gastown attachments: {gastown.attached}")
    typer.echo("\n✅ Walkthrough complete. Now run: bridge start")


@app.command("tui")
def tui(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    refresh_seconds: int = typer.Option(2, min=1, help="Refresh interval in seconds"),
    iterations: int = typer.Option(0, min=0, help="0 = run until Ctrl+C"),
    keys: bool = typer.Option(True, "--keys/--no-keys", help="Enable keyboard shortcuts (q/r/d) when TTY"),
) -> None:
    """Lightweight terminal dashboard for runtime visibility."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)

    def _bar(value: int, total: int, width: int = 18) -> str:
        if total <= 0:
            return "░" * width
        filled = max(0, min(width, int((value / total) * width)))
        return ("█" * filled) + ("░" * (width - filled))

    i = 0
    last_event = "ready"
    is_tty = sys.stdin.isatty() and sys.stdout.isatty()
    keys_enabled = keys and is_tty
    old_settings = None

    if keys_enabled:
        old_settings = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())

    # Use alternate screen buffer to avoid polluting scrollback.
    if is_tty:
        sys.stdout.write("\033[?1049h\033[?25l")
        sys.stdout.flush()

    try:
        while True:
            p_items = svc.adapters.paperclip.list_items()
            b_items = svc.adapters.beads.list_items()
            snap = dashboard_snapshot(svc.conn, len(p_items), len(b_items))

            pending = int(snap["outbox_pending"])
            sent = int(snap["outbox_sent"])
            dlq = int(snap["outbox_dlq"])
            total = max(1, pending + sent + dlq)

            health_badge = "OK" if snap["health"] == "ok" else "WARN"
            next_action = str(snap["next_action"])[:58]
            key_help = "q quit • r refresh • d outbox-drain" if keys_enabled else "Ctrl+C exit"
            ticker = str(last_event)[:58]

            lines = [
                "╭──────────────────── Bridge Live Dashboard ────────────────────╮",
                f"│ mode={cfg.mode:<6} worker={cfg.worker_id:<14} {time.strftime('%Y-%m-%d %H:%M:%S')} │",
                "├────────────────────────────────────────────────────────────────┤",
                f"│ Health: {health_badge:<56}│",
                f"│ Paperclip items: {str(snap['paperclip_items']):<6}   Beads items: {str(snap['beads_items']):<27}│",
                "├────────────────────────────────────────────────────────────────┤",
                f"│ Queue pending: {pending:<4} sent: {sent:<4} dlq: {dlq:<4} {'':<28}│",
                f"│ Queue mix    : {_bar(sent, total)}  ({sent}/{total} sent){'':<14}│",
                "├────────────────────────────────────────────────────────────────┤",
                f"│ Next: {next_action:<58}│",
                f"│ Keys: {key_help:<58}│",
                f"│ Last: {ticker:<58}│",
                "╰────────────────────────────────────────────────────────────────╯",
            ]

            if is_tty:
                sys.stdout.write("\033[2J\033[H" + "\n".join(lines) + "\n")
                sys.stdout.flush()
            else:
                typer.echo("\n".join(lines))

            i += 1
            if iterations and i >= iterations:
                break

            if keys_enabled:
                rlist, _, _ = select.select([sys.stdin], [], [], float(refresh_seconds))
                if rlist:
                    try:
                        raw = os.read(sys.stdin.fileno(), 32).decode("utf-8", "ignore").lower()
                    except Exception:
                        raw = (sys.stdin.read(1) or "").lower()

                    if "q" in raw:
                        break
                    if "d" in raw:
                        drained = svc.process_outbox()
                        last_event = f"outbox-drain sent={drained}"
                        continue
                    if "r" in raw:
                        last_event = "manual refresh"
                        continue
            else:
                time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        if old_settings is not None:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
        if is_tty:
            sys.stdout.write("\033[?25h\033[?1049l")
            sys.stdout.flush()


@app.command("status")
def status(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Operational snapshot: health + queue counters + inventory counts."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    paperclip_count = len(svc.adapters.paperclip.list_items())
    beads_count = len(svc.adapters.beads.list_items())
    snap = dashboard_snapshot(svc.conn, paperclip_count, beads_count)
    payload = {
        "mode": cfg.mode,
        "worker_id": cfg.worker_id,
        "scope_key": svc.scope_key,
        "single_writer": cfg.single_writer,
        "status_authority": cfg.status_authority,
        "health": snap["health"],
        "paperclip_items": snap["paperclip_items"],
        "beads_items": snap["beads_items"],
        "outbox": {
            "pending": snap["outbox_pending"],
            "sent": snap["outbox_sent"],
            "dlq": snap["outbox_dlq"],
        },
        "next_action": snap["next_action"],
    }
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo("\nBridge Status")
    typer.echo(
        f"mode={payload['mode']} worker={payload['worker_id']} health={payload['health']} "
        f"single_writer={payload['single_writer']} authority={payload['status_authority']}"
    )
    typer.echo(f"paperclip={payload['paperclip_items']} beads={payload['beads_items']}")
    typer.echo(
        f"outbox pending={payload['outbox']['pending']} sent={payload['outbox']['sent']} dlq={payload['outbox']['dlq']}"
    )
    typer.echo(f"next: {payload['next_action']}")


@app.command("dlq-replay")
def dlq_replay(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    limit: int = typer.Option(100, min=1, help="Max DLQ events to replay"),
) -> None:
    """Move DLQ events back to pending and attempt processing once."""
    cfg = _load(config)
    svc, logger, metrics, alerts = build_service(cfg)
    moved = db.replay_dlq(svc.conn, limit=limit)

    def _on_failure(row, exc: Exception) -> None:
        alerts.send("warning", "outbox event failed", event_id=row["event_id"], error=str(exc))

    sent = svc.process_outbox(on_failure=_on_failure)
    dlq_count = db.count_outbox_by_status(svc.conn, "dlq")
    metrics.inc("dlq_replay_runs")
    metrics.inc("outbox_sent", sent)
    metrics.set("outbox_dlq", dlq_count)
    metrics.flush()
    logger.info("dlq_replay_complete", moved=moved, sent=sent, dlq_count=dlq_count)
    typer.echo(f"dlq replay complete: moved={moved} sent={sent} dlq={dlq_count}")


@app.command("map-add")
def map_add(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    paperclip_id: str = typer.Option(..., "--paperclip-id", help="Paperclip issue UUID"),
    beads_id: str = typer.Option(..., "--beads-id", help="Beads issue id"),
    gastown_target: str | None = typer.Option(None, "--gastown-target", help="Optional gastown target"),
) -> None:
    """Add or update explicit cross-system ID mapping."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    db.put_id_map(svc.conn, svc.scope_key, paperclip_id, beads_id, gastown_target)
    typer.echo("mapping saved")


@app.command("map-list")
def map_list(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    limit: int = typer.Option(200, min=1, help="Max rows"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """List explicit ID mappings."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    rows = [dict(r) for r in db.list_id_map(svc.conn, scope_key=svc.scope_key, limit=limit)]
    if json_output:
        typer.echo(json.dumps(rows))
        return
    if not rows:
        typer.echo("no mappings")
        return
    for r in rows:
        typer.echo(f"{r['paperclip_id']} -> {r['beads_id']} (target={r.get('gastown_target')})")


@app.command("owner-set")
def owner_set(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    paperclip_id: str = typer.Option(..., "--paperclip-id", help="Paperclip issue UUID"),
    owner: str = typer.Option(..., "--owner", help="paperclip_runner|beads_runner|none"),
) -> None:
    """Set execution ownership for a task to prevent duplicate runner triggers."""
    if owner not in {"paperclip_runner", "beads_runner", "none"}:
        raise typer.BadParameter("owner must be one of: paperclip_runner, beads_runner, none")
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    db.set_execution_owner(svc.conn, svc.scope_key, paperclip_id, owner)
    typer.echo("owner saved")


@app.command("owner-list")
def owner_list(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    limit: int = typer.Option(200, min=1, help="Max rows"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """List execution ownership rules."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    rows = [dict(r) for r in db.list_execution_owner(svc.conn, scope_key=svc.scope_key, limit=limit)]
    if json_output:
        typer.echo(json.dumps(rows))
        return
    if not rows:
        typer.echo("no ownership rules")
        return
    for r in rows:
        typer.echo(f"{r['paperclip_id']} -> {r['execution_owner']}")


@app.command("phase-feedback")
def phase_feedback(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
) -> None:
    """Bounded reverse sync: execution signals from beads -> paperclip only."""
    cfg = _load(config)
    svc, logger, metrics, alerts = build_service(cfg)
    result = svc.phase_feedback_sync()

    def _on_failure(row, exc: Exception) -> None:
        alerts.send("warning", "outbox event failed", event_id=row["event_id"], error=str(exc))

    sent = svc.process_outbox(on_failure=_on_failure)
    metrics.inc("phase_feedback_runs")
    metrics.inc("outbox_sent", sent)
    metrics.flush()
    logger.info("phase_feedback_complete", queued=result.reconciled, sent=sent, skipped_owner=result.skipped_owner)
    typer.echo(f"phase-feedback complete: queued={result.reconciled} sent={sent} skipped_owner={result.skipped_owner}")


@app.command("guardrail-check")
def guardrail_check(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    paperclip_id: str = typer.Option(..., "--paperclip-id", help="Paperclip issue UUID"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Check if a task is safe/allowed to execute from Beads side (no double-run)."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    payload = svc.guardrail_check(paperclip_id)
    if json_output:
        typer.echo(json.dumps(payload))
        return
    typer.echo(f"allowed={payload['allowed']} reason={payload['reason']} owner={payload.get('owner')}")
    if payload.get("beads_id"):
        typer.echo(f"beads_id={payload['beads_id']}")


@app.command("exec-plan")
def exec_plan(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    limit: int = typer.Option(50, min=1, help="Max ready tasks"),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output"),
) -> None:
    """Show dependency-aware runnable work from Beads (mapped back to Paperclip when possible)."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    ready = svc.adapters.beads.ready_items()[:limit]

    mappings = [dict(r) for r in db.list_id_map(svc.conn, scope_key=svc.scope_key, limit=10000)]
    by_beads = {str(r["beads_id"]): str(r["paperclip_id"]) for r in mappings}

    rows = []
    for item in ready:
        rows.append(
            {
                "beads_id": item.id,
                "paperclip_id": by_beads.get(item.id),
                "status": item.status,
                "title": (item.raw or {}).get("title"),
            }
        )

    if json_output:
        typer.echo(json.dumps(rows))
        return
    if not rows:
        typer.echo("no ready tasks")
        return
    for r in rows:
        typer.echo(f"{r['beads_id']} -> {r.get('paperclip_id')} | {r.get('status')} | {r.get('title')}")


@app.command("blockers-push")
def blockers_push(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
) -> None:
    """Push blocked/in_progress/done execution signals from Beads to Paperclip (bounded path)."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)
    mappings = [dict(r) for r in db.list_id_map(svc.conn, scope_key=svc.scope_key, limit=10000)]

    queued = 0
    for m in mappings:
        pc_id = str(m["paperclip_id"])
        b_id = str(m["beads_id"])
        owner = db.get_execution_owner(svc.conn, svc.scope_key, pc_id) or "paperclip_runner"
        if owner != "beads_runner":
            continue

        deps = svc.adapters.beads.dependencies_of(b_id)
        blocked = any((d.status not in {"closed", "done"}) for d in deps)
        target = "blocked" if blocked else None

        if not blocked:
            try:
                cur = svc.adapters.beads.get_item(b_id)
                if cur.status in {"active", "in_progress"}:
                    target = "in_progress"
                elif cur.status in {"closed", "done", "hooked"}:
                    target = "done"
            except Exception:
                continue

        if not target:
            continue

        dedupe_key = f"{svc.scope_key}:feedback:auto:{pc_id}:{target}"
        db.enqueue_outbox(
            svc.conn,
            dedupe_key,
            "status_feedback",
            "beads",
            "paperclip",
            {"item_id": pc_id, "status": target, "allow_paperclip_write": True},
        )
        queued += 1

    sent = svc.process_outbox()
    typer.echo(f"blockers-push complete: queued={queued} sent={sent}")


@app.command("deps-sync")
def deps_sync(
    config: str | None = typer.Option(None, "--config", help="JSON config file path"),
    edges_file: str = typer.Option(..., "--edges-file", help="JSON file with dependency edges"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview only"),
) -> None:
    """Apply dependency edges into Beads using mapped IDs.

    edges-file format:
    [{"blocked":"<paperclip_or_beads_id>", "blocker":"<paperclip_or_beads_id>"}, ...]
    """
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)

    with open(edges_file, "r", encoding="utf-8") as f:
        edges = json.load(f)

    mappings = [dict(r) for r in db.list_id_map(svc.conn, scope_key=svc.scope_key, limit=10000)]
    pc_to_beads = {str(r["paperclip_id"]): str(r["beads_id"]) for r in mappings}

    def _resolve(x: str) -> str:
        return pc_to_beads.get(x, x)

    applied = 0
    for e in edges:
        blocked = _resolve(str(e["blocked"]))
        blocker = _resolve(str(e["blocker"]))
        if dry_run:
            typer.echo(f"would add: {blocker} blocks {blocked}")
            applied += 1
            continue
        svc.adapters.beads.add_dependency(blocked, blocker)
        applied += 1

    typer.echo(f"deps-sync complete: applied={applied} dry_run={dry_run}")


@app.command("start")
def start(
    config: str = typer.Option("config.real.local.json", "--config", help="JSON config file path"),
    agent: bool = typer.Option(False, "--agent", help="Non-interactive mode for agents/automation"),
    quiet_json: bool = typer.Option(False, "--quiet-json", help="With --agent, emit only final JSON summary"),
    skip_tui: bool = typer.Option(False, "--skip-tui", help="Skip TUI after checks/sync"),
    tui_iterations: int = typer.Option(0, min=0, help="TUI iterations (0 = continuous)", show_default=True),
    tui_refresh_seconds: int = typer.Option(2, min=1, help="TUI refresh interval seconds", show_default=True),
) -> None:
    """One-command startup: check + one sync pass + optional TUI.

    Human default: guided output + live TUI.
    Agent mode: concise, non-interactive output with no TUI.
    """
    if not agent:
        state = load_onboarding_state()
        config_exists = Path(config).exists()
        if not config_exists or not state.get("completed"):
            typer.echo("\n👋 First-run setup detected. Launching onboarding...")
            onboard(out=config, yes=False)

    cfg = _load(config)

    if not agent:
        typer.echo("\n🚀 Bridge start (human mode)")
        typer.echo(f"Using config: {config}")

    svc, logger, metrics, alerts = build_service(cfg)

    # health gate
    try:
        svc.conn.execute("SELECT 1")
        svc.adapters.paperclip.list_items()
        svc.adapters.beads.list_items()
    except Exception as exc:
        typer.echo(f"❌ health check failed: {exc}")
        raise typer.Exit(code=1)

    # one operational cycle
    svc.phase1_visibility_sync()
    p2 = svc.phase2_assignment_automation()

    def _on_failure(row, exc: Exception) -> None:
        alerts.send("warning", "outbox event failed", event_id=row["event_id"], error=str(exc))

    sent = svc.process_outbox(on_failure=_on_failure)
    rec = svc.phase3_reconcile()
    dlq = db.count_outbox_by_status(svc.conn, "dlq")

    metrics.inc("start_runs")
    metrics.inc("outbox_sent", sent)
    metrics.set("outbox_dlq", dlq)
    metrics.flush()

    if not (agent and quiet_json):
        logger.info("start_complete", sent=sent, reconciled=rec.reconciled, assignments=p2.assignments_attached, dlq=dlq)

    if agent:
        typer.echo(json.dumps({
            "status": "ok",
            "config": config,
            "phase2_assignments": p2.assignments_attached,
            "phase2_skipped_owner": p2.skipped_owner,
            "phase2_skipped_unmapped": p2.skipped_unmapped,
            "phase2_skipped_lock": p2.skipped_lock,
            "outbox_sent": sent,
            "reconciled": rec.reconciled,
            "dlq": dlq,
        }))
        return

    typer.echo("✅ Health check passed")
    typer.echo(
        "phase2 assignments queued: "
        f"{p2.assignments_attached} (skipped_owner={p2.skipped_owner}, "
        f"skipped_unmapped={p2.skipped_unmapped}, skipped_lock={p2.skipped_lock})"
    )
    typer.echo(f"outbox sent: {sent} | reconciled: {rec.reconciled} | dlq: {dlq}")

    if not skip_tui:
        typer.echo("\nOpening live dashboard... (Ctrl+C to exit)\n")
        tui(config=config, refresh_seconds=tui_refresh_seconds, iterations=tui_iterations, keys=True)


if __name__ == "__main__":
    app()
