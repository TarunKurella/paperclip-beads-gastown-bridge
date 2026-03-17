from __future__ import annotations

import signal
import time
from dataclasses import dataclass

from bridge import db
from bridge.config import RuntimeConfig
from bridge.observability import AlertSink, JsonLogger, Metrics
from bridge.service import BridgeService


@dataclass
class LoopState:
    running: bool = True
    last_phase1: float = 0
    last_phase2: float = 0
    last_phase3: float = 0
    last_outbox: float = 0


def install_signal_handlers(state: LoopState, logger: JsonLogger) -> None:
    def _stop(signum: int, _frame: object) -> None:
        logger.info("signal_received", signum=signum)
        state.running = False

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)


def run_daemon(
    service: BridgeService,
    config: RuntimeConfig,
    logger: JsonLogger,
    metrics: Metrics,
    alerts: AlertSink,
    max_loops: int | None = None,
) -> None:
    state = LoopState()
    install_signal_handlers(state, logger)
    loops = 0

    logger.info("daemon_started", worker_id=config.worker_id, mode=config.mode)
    while state.running:
        now = time.time()
        try:
            if now - state.last_phase1 >= config.intervals.phase1_seconds:
                service.phase1_visibility_sync()
                metrics.inc("phase1_runs")
                state.last_phase1 = now

            if now - state.last_phase2 >= config.intervals.phase2_seconds:
                service.phase2_assignment_automation()
                metrics.inc("phase2_runs")
                state.last_phase2 = now

            if now - state.last_phase3 >= config.intervals.phase3_seconds:
                reconciled = service.phase3_reconcile().reconciled
                metrics.inc("phase3_runs")
                metrics.inc("phase3_reconciled", reconciled)
                state.last_phase3 = now

            if now - state.last_outbox >= config.intervals.outbox_drain_seconds:
                sent = service.process_outbox()
                dlq_count = db.count_outbox_by_status(service.conn, "dlq")
                metrics.inc("outbox_drains")
                metrics.inc("outbox_sent", sent)
                metrics.set("outbox_dlq", dlq_count)
                if dlq_count >= config.alerts.dlq_warn_threshold:
                    alerts.send("warning", "dlq threshold reached", dlq_count=dlq_count)
                state.last_outbox = now

            metrics.flush()
        except Exception as exc:
            metrics.inc("loop_errors")
            logger.error("daemon_loop_error", error=str(exc))
            alerts.send("error", "daemon loop error", error=str(exc))

        loops += 1
        if max_loops is not None and loops >= max_loops:
            break
        time.sleep(config.intervals.loop_sleep_seconds)

    logger.info("daemon_stopped", loops=loops)
