from __future__ import annotations

from typing import TYPE_CHECKING

from schedule import every
from task import TaskManager, run_all_tasks, stop_all_tasks, task

from .log_utils import prune_sync_logs
from .sync_service import sync_configured_users

if TYPE_CHECKING:
    from flask import Flask

_task_manager = TaskManager()
_scheduler_started = False


def init_task_scheduler(app: "Flask") -> None:
    """Initialize background tasks for syncs and log retention."""

    global _scheduler_started

    if _scheduler_started:
        return

    log_age = max(1, int(app.config.get("LOG_AGE", 90)))
    retention_job = every(12).hours

    @task(retention_job, name="sync_log_retention", threaded=True)
    def _sync_log_retention() -> None:
        with app.app_context():
            removed = prune_sync_logs(log_age)
            if removed:
                app.logger.info("Sync log retention removed %s file(s)", removed)

    setattr(_task_manager, "sync_log_retention", _sync_log_retention)

    if app.config.get("TLINK_SYNC_ENABLED", True):
        interval = max(5, int(app.config.get("TLINK_SYNC_INTERVAL_SECONDS", 60)))
        schedule_job = every(interval).seconds

        @task(schedule_job, name="tlink_device_sync", threaded=True)
        def _tlink_device_sync() -> None:
            with app.app_context():
                app.logger.info("TLINK device sync task started")
                try:
                    summary = sync_configured_users()
                except Exception:
                    app.logger.exception("TLINK device sync task failed")
                    raise
                else:
                    app.logger.info(
                        "TLINK device sync task completed: users=%s devices=%s readings=%s",
                        summary.get("users", 0),
                        summary.get("devices", 0),
                        summary.get("readings", 0),
                    )

        setattr(_task_manager, "tlink_device_sync", _tlink_device_sync)
    else:
        app.logger.info("TLINK sync task disabled via TLINK_SYNC_ENABLED")

    stop_all_tasks(_task_manager)
    run_all_tasks(_task_manager)
    _scheduler_started = True