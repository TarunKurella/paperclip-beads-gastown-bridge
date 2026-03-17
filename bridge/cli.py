from __future__ import annotations

from pathlib import Path

import typer

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.service import BridgeService

app = typer.Typer(help="Paperclip/Beads/Gastown bridge")


def _service(db_path: str) -> BridgeService:
    conn = db.connect(db_path)
    migrations_dir = str(Path(__file__).parent / "migrations")
    db.migrate(conn, migrations_dir)

    # Placeholder runtime adapters. Swap with real adapters in production wiring.
    paperclip = InMemoryPaperclip(
        {
            "1": WorkItem(id="1", status="todo", assignee="alice"),
            "2": WorkItem(id="2", status="in_progress", assignee=None),
        }
    )
    beads = InMemoryBeads(
        {
            "1": WorkItem(id="1", status="new"),
            "2": WorkItem(id="2", status="active"),
        }
    )
    gastown = InMemoryGastown()
    return BridgeService(conn, AdapterBundle(paperclip=paperclip, beads=beads, gastown=gastown))


@app.command()
def migrate(db_path: str = typer.Option("bridge.db", help="SQLite file path")) -> None:
    conn = db.connect(db_path)
    db.migrate(conn, str(Path(__file__).parent / "migrations"))
    typer.echo("migrations applied")


@app.command("phase1-sync")
def phase1_sync(db_path: str = "bridge.db") -> None:
    svc = _service(db_path)
    svc.phase1_visibility_sync()
    sent = svc.process_outbox()
    typer.echo(f"phase1 complete: sent={sent}")


@app.command("phase2-assign")
def phase2_assign(db_path: str = "bridge.db") -> None:
    svc = _service(db_path)
    svc.phase2_assignment_automation()
    sent = svc.process_outbox()
    typer.echo(f"phase2 complete: sent={sent}")


@app.command("phase3-reconcile")
def phase3_reconcile(db_path: str = "bridge.db", worker_id: str = "worker-1") -> None:
    svc = _service(db_path)
    svc.worker_id = worker_id
    result = svc.phase3_reconcile()
    typer.echo(f"phase3 complete: reconciled={result.reconciled}")


if __name__ == "__main__":
    app()
