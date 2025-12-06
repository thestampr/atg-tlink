from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import requests
from flask import current_app

from .atg_export import export_atg_snapshot
from .db import (
    get_connection,
    insert_reading,
    upsert_device,
    upsert_sensor,
)
from .log_utils import write_sync_log
from .tlink import get_oauth_client
from .utils import coerce_datetime, to_storage_timestamp

Payload = Dict[str, Any]


def process_push_payload(payload: Payload) -> int:
    device_id = payload.get("deviceId")
    user_id = payload.get("deviceUserid")
    sensors = payload.get("sensorsDates") or []

    if not device_id or not user_id or not sensors:
        raise ValueError("deviceId, deviceUserid, and sensorsDates are required")

    parent_user_id = payload.get("parentUserId")
    push_time = coerce_datetime(payload.get("time")) or datetime.utcnow()
    push_time_str = to_storage_timestamp(push_time)

    conn = get_connection()
    processed = 0
    try:
        device_row = upsert_device(
            conn,
            None,
            device_id,
            parent_user_id,
            payload.get("deviceName") or payload.get("device_name"),
            payload.get("deviceNo") or payload.get("device_no") or payload.get("rawData"),
            _coerce_int(payload.get("groupId") or payload.get("group_id")),
            _safe_str(payload.get("lat")),
            _safe_str(payload.get("lng")),
            payload.get("productId") or payload.get("product_id"),
            payload.get("productType") or payload.get("product_type"),
            payload.get("protocolLabel") or payload.get("protocol_label"),
            payload.get("flag"),
            payload.get("rawData"),
            push_time_str,
        )

        for entry in sensors:
            sensor_external_id = entry.get("sensorsId")
            if sensor_external_id is None:
                continue

            sensor_row = upsert_sensor(
                conn,
                device_row["id"],
                sensor_external_id,
                entry.get("sensorsTypeId"),
                entry.get("sensorName") or entry.get("sensor_name"),
                _interpret_bool(entry.get("isLine")),
                _interpret_bool(entry.get("isAlarm")),
                entry.get("unit"),
                entry.get("value") or entry.get("reVal"),
                push_time_str,
            )

            insert_reading(
                conn,
                sensor_row["id"],
                push_time_str,
                entry.get("times"),
                _interpret_bool(entry.get("isAlarm")),
                _interpret_bool(entry.get("isLine")),
                entry.get("reVal"),
                entry.get("value"),
                payload.get("rawData"),
            )
            processed += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return processed


def sync_user_devices(user_id: int, overrides: Optional[Dict[str, Any]] = None) -> Tuple[int, int]:
    config = current_app.config
    page_size = config.get("TLINK_SYNC_PAGE_SIZE", 10)

    params: Dict[str, Any] = {
        "userId": user_id,
        "currPage": 1,
        "pageSize": page_size,
    }
    if overrides:
        params.update({k: v for k, v in overrides.items() if v is not None})

    try:
        payload = _invoke_tlink_sensor_api(params)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        _log_sync_event(
            user_id=user_id,
            device_id=user_id,
            sensors=[],
            readings=0,
            status="error",
            http_status=status,
            message=f"TLINK HTTP error: {exc}",
        )
        raise
    except Exception as exc:
        _log_sync_event(
            user_id=user_id,
            device_id=user_id,
            sensors=[],
            readings=0,
            status="error",
            http_status=None,
            message=str(exc),
        )
        raise
    if payload.get("flag") != "00":
        raise RuntimeError(f"TLINK responded with flag {payload.get('flag')!r}")

    devices = payload.get("dataList") or []
    total_devices = 0
    total_readings = 0

    for device in devices:
        normalized_payload = _payload_from_remote_device(device, user_id, payload.get("flag"))
        sensor_entries = list(normalized_payload.get("sensorsDates") or [])
        device_external_id = normalized_payload.get("deviceId")

        if not device_external_id:
            _log_sync_event(
                user_id=user_id,
                device_id=user_id,
                sensors=sensor_entries,
                readings=0,
                status="error",
                http_status=None,
                message="Missing deviceId in payload",
            )
            continue

        if not sensor_entries:
            _log_sync_event(
                user_id=user_id,
                device_id=device_external_id,
                sensors=[],
                readings=0,
                status="error",
                http_status=None,
                message="No sensors in payload",
            )
            continue
        try:
            stored = process_push_payload(normalized_payload)
        except ValueError as exc:
            _log_sync_event(
                user_id=user_id,
                device_id=device_external_id,
                sensors=sensor_entries,
                readings=0,
                status="error",
                http_status=None,
                message=str(exc),
            )
            continue
        except Exception as exc:
            _log_sync_event(
                user_id=user_id,
                device_id=device_external_id,
                sensors=sensor_entries,
                readings=0,
                status="error",
                http_status=None,
                message=str(exc),
            )
            raise
        else:
            _log_sync_event(
                user_id=user_id,
                device_id=device_external_id,
                sensors=sensor_entries,
                readings=stored,
                status="success",
                http_status=200,
                message="sync complete",
            )
        total_devices += 1
        total_readings += stored

    return total_devices, total_readings


def sync_configured_users() -> Dict[str, int]:
    config = current_app.config
    user_id = config.get("TLINK_ACCOUNT_NUMBER", 0)
    summary = {"users": 0, "devices": 0, "readings": 0}

    if not user_id:
        current_app.logger.debug("TLINK sync skipped: no TLINK_ACCOUNT_NUMBER configured")
        return summary

    try:
        devices, readings = sync_user_devices(user_id)
        summary["users"] += 1
        summary["devices"] += devices
        summary["readings"] += readings
        current_app.logger.info(
            "TLINK sync completed for user %s (devices=%s, readings=%s)",
            user_id,
            devices,
            readings,
        )
        export_atg_snapshot()
    except Exception as exc:  # pragma: no cover - logged for observability
        current_app.logger.exception("TLINK sync failed for user %s: %s", user_id, exc)

    return summary


def _invoke_tlink_sensor_api(params: Dict[str, Any]) -> Dict[str, Any]:
    config = current_app.config
    base = config.get("TLINK_BASE_URL")
    path = (config.get("TLINK_SENSOR_DATA_PATH") or "").lstrip("/")
    if not base or not path:
        raise ValueError("TLINK base URL or path is not configured")

    url = f"{base}/{path}"
    timeout = config.get("TLINK_HTTP_TIMEOUT", 30)
    method = config.get("TLINK_SENSOR_HTTP_METHOD", "GET").upper()
    client = get_oauth_client()

    for attempt in range(2):
        headers = {"Content-Type": "application/json"}
        if config.get("TLINK_APP_ID"):
            headers["tlinkAppId"] = config["TLINK_APP_ID"]

        try:
            headers["Authorization"] = client.get_authorization_header()
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc

        if method == "POST":
            response = requests.post(url, headers=headers, json=params, timeout=timeout)
        else:
            response = requests.get(url, headers=headers, json=params, timeout=timeout)

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status == 401 and attempt == 0:
                current_app.logger.warning("TLINK access token rejected; refreshing and retrying")
                client.invalidate_token()
                continue
            raise

        try:
            return response.json()
        except ValueError as exc:
            raise ValueError("TLINK response did not contain JSON") from exc

        raise RuntimeError("TLINK request failed after retry")


def _payload_from_remote_device(device: Dict[str, Any], default_user_id: int, default_flag: Optional[str]) -> Dict[str, Any]:
    sensors = device.get("sensorsList") or []
    sensor_entries = []
    for sensor in sensors:
        normalized = _sensor_entry_from_remote(sensor)
        if normalized:
            sensor_entries.append(normalized)

    base_time = device.get("updateDate") or device.get("createDate")
    if not base_time and sensor_entries:
        base_time = sensor_entries[0].get("times")

    return {
        "flag": device.get("flag") or default_flag or "sync",
        "deviceUserid": device.get("userId") or default_user_id,
        "parentUserId": device.get("parentUserId") or device.get("parentUser"),
        "sensorsDates": sensor_entries,
        "time": base_time,
        "rawData": device.get("deviceNo"),
        "deviceId": device.get("id") or device.get("deviceId"),
        "deviceName": device.get("deviceName") or device.get("device_name"),
        "deviceNo": device.get("deviceNo") or device.get("device_no"),
        "groupId": device.get("groupId") or device.get("group_id"),
        "lat": device.get("lat"),
        "lng": device.get("lng"),
        "productId": device.get("productId") or device.get("product_id"),
        "productType": device.get("productType") or device.get("product_type"),
        "protocolLabel": device.get("protocolLabel") or device.get("protocol_label"),
    }


def _sensor_entry_from_remote(sensor: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sensor_id = (
        sensor.get("sensorsId")
        or sensor.get("sensorId")
        or sensor.get("id")
    )
    if sensor_id is None:
        return None

    timestamp = sensor.get("updateDate") or sensor.get("heartbeatDate")
    return {
        "times": timestamp,
        "sensorsId": sensor_id,
        "sensorsTypeId": sensor.get("sensorTypeId"),
        "sensorName": sensor.get("sensorName") or sensor.get("sensor_name"),
        "isLine": sensor.get("isLine"),
        "isAlarm": sensor.get("isAlarms"),
        "reVal": sensor.get("send_value") or sensor.get("value"),
        "value": sensor.get("value"),
        "unit": sensor.get("unit"),
    }


def _interpret_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes"}:
            return True
        if normalized in {"0", "false", "f", "no"}:
            return False
    return bool(value)


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _log_sync_event(
    *,
    user_id: int,
    device_id: Any,
    sensors: Optional[list],
    readings: int,
    status: str,
    http_status: Optional[int],
    message: str,
) -> None:
    try:
        write_sync_log(
            user_id=user_id,
            device_id=device_id,
            sensors=sensors or [],
            readings=readings,
            status=status,
            http_status=http_status,
            message=message,
        )
    except Exception:
        current_app.logger.exception("Failed to persist sync log for device %s", device_id)
