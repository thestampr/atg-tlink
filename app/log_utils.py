from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, DefaultDict, Dict, Iterable, List, Optional, Tuple, Union

from flask import current_app


def _base_log_dir() -> Path:
    configured = current_app.config.get("SYNC_LOG_DIR")
    return Path(configured) if configured else Path(current_app.instance_path) / "logs"


def _log_base_dir() -> Path:
    base_dir = _base_log_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _device_directory(device_id: Union[int, str], ensure: bool = False) -> Path:
    base_dir = _base_log_dir()
    device_path = base_dir / str(device_id)
    if ensure:
        device_path.mkdir(parents=True, exist_ok=True)
    return device_path


def _sanitize_message(message: str) -> str:
    return message.replace("\n", " ").strip()


def _sensor_snapshot(entries: Iterable[dict]) -> List[dict]:
    snapshot = []
    for sensor in entries:
        snapshot.append(
            {
                "sensorId": sensor.get("sensorsId") or sensor.get("sensorId") or sensor.get("id"),
                "sensorTypeId": sensor.get("sensorsTypeId") or sensor.get("sensorTypeId"),
                "value": sensor.get("value"),
                "reVal": sensor.get("reVal") or sensor.get("send_value"),
                "isAlarm": sensor.get("isAlarm") or sensor.get("isAlarms"),
                "isLine": sensor.get("isLine"),
                "unit": sensor.get("unit"),
                "timestamp": sensor.get("times") or sensor.get("updateDate") or sensor.get("heartbeatDate"),
            }
        )
    return snapshot


def write_sync_log(
    *,
    user_id: int,
    device_id: Union[int, str],
    sensors: Iterable[dict],
    readings: int,
    status: str,
    http_status: Optional[int],
    message: str,
) -> None:
    base_dir = _log_base_dir()
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    device_folder = _device_directory(device_id, ensure=True)
    file_path = device_folder / f"device{device_id}-{date_str}.log"

    sensor_snapshot = _sensor_snapshot(sensors)
    encoded_sensors = json.dumps(sensor_snapshot, separators=(",", ":"), ensure_ascii=True)
    http_value = http_status if http_status is not None else "NA"
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = (
        f"{timestamp} | status={status} | user={user_id} | device={device_id} | "
        f"sensors={len(sensor_snapshot)} | readings={readings} | http={http_value} | "
        f"sensors_json={encoded_sensors} | message={_sanitize_message(message)}\n"
    )

    with open(file_path, "a", encoding="utf-8") as handle:
        handle.write(line)


def prune_sync_logs(max_age_days: int) -> int:
    if max_age_days <= 0:
        return 0

    base_dir = _base_log_dir()
    if not base_dir.exists() or not base_dir.is_dir():
        return 0

    cutoff = datetime.utcnow() - timedelta(days=max_age_days)
    removed = 0
    for device_dir in base_dir.iterdir():
        if not device_dir.is_dir():
            continue
        for log_file in device_dir.iterdir():
            try:
                mtime = datetime.utcfromtimestamp(log_file.stat().st_mtime)
            except FileNotFoundError:
                continue
            if mtime < cutoff:
                try:
                    log_file.unlink()
                    removed += 1
                except FileNotFoundError:
                    continue
        try:
            if not any(device_dir.iterdir()):
                device_dir.rmdir()
        except (FileNotFoundError, OSError):
            continue

    return removed


def _parse_timestamp(value: str) -> Optional[datetime]:
    value = value.strip()
    if not value:
        return None
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(tz=None).replace(tzinfo=None)
    return parsed


def _parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    if not line.strip():
        return None
    parts = [segment.strip() for segment in line.split("|") if segment.strip()]
    if not parts:
        return None

    timestamp = _parse_timestamp(parts[0])
    if timestamp is None:
        return None

    fields: Dict[str, str] = {}
    for token in parts[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key.strip()] = value.strip()

    try:
        user_id = int(fields.get("user", "0"))
        device_id = int(fields.get("device", "0"))
    except ValueError:
        return None

    sensors_raw = fields.get("sensors_json", "[]")
    try:
        sensors = json.loads(sensors_raw)
    except json.JSONDecodeError:
        sensors = []

    http_status = fields.get("http")
    http_value: Optional[int] = None
    if http_status and http_status.upper() != "NA":
        try:
            http_value = int(http_status)
        except ValueError:
            http_value = None

    return {
        "timestamp": timestamp,
        "status": fields.get("status", "unknown"),
        "user_id": user_id,
        "device_id": device_id,
        "sensors": sensors,
        "http_status": http_value,
        "message": fields.get("message", ""),
    }


def _interpret_flag(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "on"}:
            return True
        if normalized in {"0", "false", "f", "no", "off"}:
            return False
    return None


def load_sensor_history_from_logs(
    device_id: int,
    per_sensor_limit: int,
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> Dict[int, List[Dict[str, Any]]]:
    history: DefaultDict[int, List[Dict[str, Any]]] = defaultdict(list)
    if per_sensor_limit <= 0:
        return history

    device_dir = _device_directory(device_id, ensure=False)
    if not device_dir.exists():
        return history

    files = sorted(device_dir.glob(f"device{device_id}-*.log"), reverse=True)
    if not files:
        return history

    for file_path in files:
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue

        for line in reversed(lines):
            entry = _parse_log_line(line)
            if not entry:
                continue
            if entry["device_id"] != device_id:
                continue

            entry_time = entry["timestamp"]
            if start_time and entry_time < start_time:
                continue
            if end_time and entry_time > end_time:
                continue

            for sensor in entry["sensors"]:
                sensor_id_int = _coerce_sensor_id(sensor.get("sensorId"))
                if sensor_id_int is None:
                    continue

                readings = history[sensor_id_int]
                if len(readings) >= per_sensor_limit:
                    continue

                recorded_at = entry_time.replace(microsecond=0).isoformat()
                readings.append(
                    {
                        "recordedAt": recorded_at,
                        "sensorTimestamp": sensor.get("timestamp"),
                        "isAlarm": _interpret_flag(sensor.get("isAlarm") or sensor.get("isAlarms")),
                        "isLine": _interpret_flag(sensor.get("isLine")),
                        "rawValue": sensor.get("value"),
                        "value": sensor.get("reVal") if sensor.get("reVal") is not None else sensor.get("value"),
                    }
                )

    return dict(history)


def query_sync_logs(
    *,
    user_id: int,
    device_id: int,
    sensor_id: Optional[int],
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    status: Optional[str],
    page: int,
    page_size: int,
) -> Tuple[List[Dict[str, Any]], bool]:
    device_dir = _device_directory(device_id, ensure=False)
    if not device_dir.exists():
        return [], False

    normalized_status = status.lower() if status else None
    offset = max(0, (page - 1) * page_size)
    files = sorted(device_dir.glob(f"device{device_id}-*.log"), reverse=True)
    entries: List[Dict[str, Any]] = []
    matched = 0

    for file_path in files:
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            continue

        for line in reversed(lines):
            entry = _parse_log_line(line)
            if not entry:
                continue
            if entry["device_id"] != device_id or entry["user_id"] != user_id:
                continue

            entry_time = entry["timestamp"]
            if start_time and entry_time < start_time:
                continue
            if end_time and entry_time > end_time:
                continue

            if normalized_status and entry["status"].lower() != normalized_status:
                continue

            sensors = entry.get("sensors") or []
            if sensor_id is not None:
                filtered = [s for s in sensors if _sensor_matches(s, sensor_id)]
                if not filtered:
                    continue
                entry = dict(entry)
                entry["sensors"] = filtered

            matched += 1
            if matched <= offset:
                continue

            if len(entries) < page_size:
                entries.append(entry)
            else:
                return entries, True

    return entries, False


def _coerce_sensor_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _sensor_matches(sensor: Dict[str, Any], desired: int) -> bool:
    sensor_id = (
        sensor.get("sensorId")
        or sensor.get("sensor_id")
        or sensor.get("id")
    )
    actual = _coerce_sensor_id(sensor_id)
    return actual == desired
