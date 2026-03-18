from __future__ import annotations

from pathlib import Path

from bridge import db
from bridge.adapters.base import AdapterBundle
from bridge.adapters.beads import BeadsCLIAdapter
from bridge.adapters.gastown import GastownCLIAdapter
from bridge.adapters.paperclip import PaperclipHTTPAdapter
from bridge.config import RuntimeConfig
from bridge.mock_adapters import InMemoryBeads, InMemoryGastown, InMemoryPaperclip
from bridge.models import WorkItem
from bridge.observability import AlertSink, JsonLogger, Metrics
from bridge.service import BridgeService


def build_adapters(config: RuntimeConfig) -> AdapterBundle:
    if config.mode == "real":
        return AdapterBundle(
            paperclip=PaperclipHTTPAdapter(
                base_url=str(config.paperclip_base_url),
                token=config.paperclip_token,
                company_id=config.paperclip_company_id,
            ),
            beads=BeadsCLIAdapter(bin_name=config.beads_bin),
            gastown=GastownCLIAdapter(bin_name=config.gastown_bin),
        )

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
    return AdapterBundle(paperclip=paperclip, beads=beads, gastown=gastown)


def build_service(config: RuntimeConfig) -> tuple[BridgeService, JsonLogger, Metrics, AlertSink]:
    conn = db.connect(config.db_path)
    db.migrate(conn, str(Path(__file__).parent / "migrations"))
    adapters = build_adapters(config)
    svc = BridgeService(
        conn,
        adapters,
        worker_id=config.worker_id,
        single_writer=config.single_writer,
        status_authority=config.status_authority,
        scope_key=config.paperclip_company_id or "default",
    )
    logger = JsonLogger(component="bridge-runtime")
    metrics = Metrics(file_path=config.metrics.file_path)
    alerts = AlertSink(logger=logger, webhook_url=config.alerts.webhook_url)
    return svc, logger, metrics, alerts
