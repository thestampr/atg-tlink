from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Optional

from flask import current_app


class LogEntry:
    __slots__ = ("timestamp", "status", "user_id", "device_id", "sensors", "http", "message")

    def __init__(
        self,
        *,
        timestamp: datetime,
        status: str,
        user_id: int,
        device_id: int,
        sensors: List[dict],
        http: Optional[int],
        message: str,
    ) -> None:
        self.timestamp = timestamp
        self.status = status
        self.user_id = user_id
        self.device_id = device_id
        self.sensors = sensors
        self.http = http
        self.message = message


def _log_directory(device_id: int) -> Path:
    base_dir = current_app.config.get("SYNC_LOG_DIR")
    if not base_dir:
        base_dir = Path(current_app.instance_path) / "logs"
    path = Path(base_dir) / str(device_id)
    return path


def _parse_line(line: str) -> Optional[LogEntry]:
    try:
        prefix, sensors_json_part, message_part = line.split("| sensors_json=", 1)[0], None, None
    except ValueError:
        return None