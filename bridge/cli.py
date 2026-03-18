from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.config import AlertConfig, ConfigError, MetricsConfig, RuntimeConfig, load_config
from bridge.daemon import run_daemon
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
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
    svc.phase2_assignment_automation()
    sent = svc.process_outbox()
    metrics.inc("phase2_runs")
    metrics.inc("outbox_sent", sent)
    metrics.flush()
    logger.info("phase2_complete", sent=sent)
    typer.echo(f"phase2 complete: sent={sent}")


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
    else:
        paperclip_url = typer.prompt("Paperclip base URL", default=default_url)
        beads_bin = typer.prompt("Beads binary", default=default_beads)
        gastown_bin = typer.prompt("Gastown binary", default=default_gastown)
        worker_id = typer.prompt("Worker ID", default="node-1")

    cfg = RuntimeConfig(
        mode="real",
        db_path="./state/bridge.db",
        worker_id=worker_id,
        paperclip_base_url=paperclip_url,
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
) -> None:
    """Lightweight terminal dashboard for runtime visibility."""
    cfg = _load(config)
    svc, _logger, _metrics, _alerts = build_service(cfg)

    i = 0
    try:
        while True:
            p_items = svc.adapters.paperclip.list_items()
            b_items = svc.adapters.beads.list_items()
            snap = dashboard_snapshot(svc.conn, len(p_items), len(b_items))

            print("\033[2J\033[H", end="")
            health_badge = "🟢 OK" if snap["health"] == "ok" else "🟠 WARN"
            typer.echo("Bridge Live Dashboard")
            typer.echo(f"mode={cfg.mode} worker={cfg.worker_id} time={time.strftime('%Y-%m-%d %H:%M:%S')}")
            typer.echo("=" * 58)
            typer.echo(f"HEALTH  : {health_badge}")
            typer.echo("-" * 58)
            typer.echo("SYSTEM")
            typer.echo(f"  paperclip_items : {snap['paperclip_items']}")
            typer.echo(f"  beads_items     : {snap['beads_items']}")
            typer.echo("QUEUE")
            typer.echo(f"  outbox_pending  : {snap['outbox_pending']}")
            typer.echo(f"  outbox_sent     : {snap['outbox_sent']}")
            typer.echo(f"  outbox_dlq      : {snap['outbox_dlq']}")
            typer.echo("NEXT ACTION")
            typer.echo(f"  {snap['next_action']}")
            typer.echo("\nCtrl+C to exit")

            i += 1
            if iterations and i >= iterations:
                break
            time.sleep(refresh_seconds)
    except KeyboardInterrupt:
        pass


@app.command("start")
def start(
    config: str = typer.Option("config.real.local.json", "--config", help="JSON config file path"),
    agent: bool = typer.Option(False, "--agent", help="Non-interactive mode for agents/automation"),
    quiet_json: bool = typer.Option(False, "--quiet-json", help="With --agent, emit only final JSON summary"),
    skip_tui: bool = typer.Option(False, "--skip-tui", help="Skip TUI after checks/sync"),
    tui_iterations: int = typer.Option(0, min=0, help="TUI iterations (0 = continuous)", show_default=True),
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
            "outbox_sent": sent,
            "reconciled": rec.reconciled,
            "dlq": dlq,
        }))
        return

    typer.echo("✅ Health check passed")
    typer.echo(f"phase2 assignments queued: {p2.assignments_attached}")
    typer.echo(f"outbox sent: {sent} | reconciled: {rec.reconciled} | dlq: {dlq}")

    if not skip_tui:
        typer.echo("\nOpening live dashboard... (Ctrl+C to exit)\n")
        tui(config=config, iterations=tui_iterations)


if __name__ == "__main__":
    app()
