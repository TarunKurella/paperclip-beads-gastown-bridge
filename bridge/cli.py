from __future__ import annotations

import json
from pathlib import Path

import typer

from bridge import db
from bridge.config import ConfigError, load_config
from bridge.daemon import run_daemon
from bridge.runtime import build_service

app = typer.Typer(help="Paperclip/Beads/Gastown bridge")


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


if __name__ == "__main__":
    app()
