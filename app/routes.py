from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

import mysql.connector
from flask import Blueprint, current_app, jsonify, request
from markupsafe import escape

from .db import (
    count_devices,
    fetch_devices,
    fetch_device_by_external_id,
    fetch_latest_sensor_reading,
    fetch_sensors,
    fetch_sensor_history,
    fetch_user_by_id,
    get_connection,
    list_unassigned_devices,
    register_user_account,
)
from .log_utils import load_sensor_history_from_logs, query_sync_logs
from .sync_service import process_push_payload
from .utils import coerce_datetime, normalize_timestamp, to_storage_timestamp, verify_signature

if TYPE_CHECKING:
    from flask import Response


api_bp = Blueprint("api", __name__)


@api_bp.route("/webhooks/tlink", methods=["POST"])
def ingest_push() -> Response:
    raw_payload = request.get_data(cache=True)
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "Invalid or empty JSON body"}), 400

    shared_secret = current_app.config.get("PUSH_WEBHOOK_SECRET", "")
    signature_valid = verify_signature(
        shared_secret, raw_payload, request.headers.get("X-TLink-Signature")
    )

    if not signature_valid:
        return jsonify({"error": "Invalid webhook signature"}), 401

    try:
        stored = process_push_payload(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"status": "ok", "storedReadings": stored})


@api_bp.route("/devices", methods=["GET"])
def list_devices() -> Response:
    conn = get_connection()
    owner_id = request.args.get("ownerId")
    owner = None
    if owner_id:
        owner = fetch_user_by_id(conn, owner_id)
        if not owner:
            return jsonify({"error": "User not found"}), 404

    device_filter = request.args.get("deviceId", type=int)
    start_time = coerce_datetime(request.args.get("startTime"))
    end_time = coerce_datetime(request.args.get("endTime"))
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = request.args.get(
        "pageSize", current_app.config["DEFAULT_PAGE_SIZE"], type=int
    )
    page_size = max(1, min(page_size, current_app.config["MAX_PAGE_SIZE"]))
    history_limit = request.args.get(
        "historyLimit", current_app.config["HISTORY_LIMIT"], type=int
    )
    history_limit = max(1, history_limit)

    total_devices = count_devices(conn, owner_id, device_filter)
    offset = (page - 1) * page_size
    device_rows = fetch_devices(conn, owner_id, device_filter, page_size, offset)

    device_payload = []
    start_bound = to_storage_timestamp(start_time)
    end_bound = to_storage_timestamp(end_time)

    for device in device_rows:
        sensors = fetch_sensors(conn, device["id"])
        sensor_payload = []
        for sensor in sensors:
            history_rows = fetch_sensor_history(
                conn,
                sensor["id"],
                start_bound,
                end_bound,
                history_limit,
            )
            sensor_payload.append(
                {
                    **_sensor_summary(sensor, device["external_id"]),
                    "history": [_reading_dict(row) for row in history_rows],
                }
            )

        device_payload.append(
            {
                **_device_summary(device),
                "sensors": sensor_payload,
            }
        )

    total_pages = (total_devices + page_size - 1) // page_size if page_size else 0

    response_payload = {
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total_devices,
            "pages": total_pages,
        },
        "devices": device_payload,
    }
    if owner:
        response_payload["user"] = _user_dict(owner)

    return jsonify(response_payload)


@api_bp.route("/devices/<int:device_id>/latest", methods=["GET"])
def get_device_latest(device_id: int) -> Response:
    conn = get_connection()
    owner_id = request.args.get("ownerId")
    owner = None
    if owner_id:
        owner = fetch_user_by_id(conn, owner_id)
        if not owner:
            return jsonify({"error": "User not found"}), 404

    device = _find_device(conn, device_id, owner_id)
    if not device:
        message = "Device not found for user" if owner else "Device not found"
        return jsonify({"error": message}), 404

    sensors = []
    for sensor in fetch_sensors(conn, device["id"]):
        latest_reading = fetch_latest_sensor_reading(conn, sensor["id"])
        sensors.append(
            {
                **_sensor_summary(sensor, device["external_id"]),
                "latest": _reading_dict(latest_reading) if latest_reading else None,
            }
        )

    response = {"device": _device_summary(device), "sensors": sensors}
    if owner:
        response["user"] = _user_dict(owner)
    return jsonify(response)


@api_bp.route("/devices/<int:device_id>/history", methods=["GET"])
def get_device_history(device_id: int) -> Response:
    conn = get_connection()
    owner_id = request.args.get("ownerId")
    owner = None
    if owner_id:
        owner = fetch_user_by_id(conn, owner_id)
        if not owner:
            return jsonify({"error": "User not found"}), 404

    device = _find_device(conn, device_id, owner_id)
    if not device:
        message = "Device not found for user" if owner else "Device not found"
        return jsonify({"error": message}), 404

    start_time = coerce_datetime(request.args.get("startTime"))
    end_time = coerce_datetime(request.args.get("endTime"))
    history_limit = request.args.get(
        "historyLimit", current_app.config["HISTORY_LIMIT"], type=int
    )
    history_limit = max(1, history_limit)

    history_map = load_sensor_history_from_logs(
        device["external_id"], history_limit, start_time, end_time
    )

    sensors_payload = []
    known_sensor_ids = set()
    for sensor in fetch_sensors(conn, device["id"]):
        sensor_id = sensor["external_id"]
        known_sensor_ids.add(sensor_id)
        sensors_payload.append(
            {
                **_sensor_summary(sensor, device["external_id"]),
                "history": history_map.get(sensor_id, []),
            }
        )

    for sensor_id, entries in history_map.items():
        if sensor_id in known_sensor_ids:
            continue
        sensors_payload.append(
            {
                "sensorId": sensor_id,
                "deviceId": device["external_id"],
                "sensorTypeId": None,
                "isAlarm": None,
                "isLine": None,
                "latestValue": None,
                "latestRecordedAt": None,
                "history": entries[:history_limit],
            }
        )

    response = {
        "device": _device_summary(device),
        "sensors": sensors_payload,
    }
    if owner:
        response["user"] = _user_dict(owner)
    return jsonify(response)


@api_bp.route("/logs/<int:device_id>", methods=["GET"])
@api_bp.route("/logs/<int:device_id>/<int:sensor_id>", methods=["GET"])
def get_device_logs(device_id: int, sensor_id: Optional[int] = None) -> Response:
    conn = get_connection()
    owner_id = request.args.get("ownerId")
    owner = None
    if owner_id:
        owner = fetch_user_by_id(conn, owner_id)
        if not owner:
            return jsonify({"error": "User not found"}), 404

    device = _find_device(conn, device_id, owner_id)
    if not device:
        message = "Device not found for user" if owner else "Device not found"
        return jsonify({"error": message}), 404

    start_time = coerce_datetime(request.args.get("startTime"))
    end_time = coerce_datetime(request.args.get("endTime"))
    status_filter = request.args.get("status")
    if status_filter:
        status_filter = status_filter.strip().lower()

    if sensor_id is not None:
        sensor_rows = fetch_sensors(conn, device["id"])
        if not any(row["external_id"] == sensor_id for row in sensor_rows):
            return jsonify({"error": "Sensor not found for device"}), 404

    page = max(request.args.get("page", 1, type=int), 1)
    page_size = request.args.get(
        "pageSize", current_app.config["DEFAULT_PAGE_SIZE"], type=int
    )
    page_size = max(1, min(page_size, current_app.config["MAX_PAGE_SIZE"]))

    tlink_account = current_app.config.get("TLINK_ACCOUNT_NUMBER")
    if not tlink_account:
        return jsonify({"error": "TLINK_ACCOUNT_NUMBER is not configured"}), 500

    entries, has_more = query_sync_logs(
        user_id=int(tlink_account),
        device_id=device["external_id"],
        sensor_id=sensor_id,
        start_time=start_time,
        end_time=end_time,
        status=status_filter,
        page=page,
        page_size=page_size,
    )

    logs_payload = [_log_entry_payload(entry) for entry in entries]

    response = {
        "device": _device_summary(device),
        "logs": logs_payload,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "returned": len(logs_payload),
            "hasMore": has_more,
        },
    }
    if owner:
        response["user"] = _user_dict(owner)
    return jsonify(response)


@api_bp.route("/users/register", methods=["POST"])
def register_user() -> Response:
    payload = request.get_json(silent=True)
    if payload is None or not isinstance(payload, dict):
        payload = request.form.to_dict()
    if not payload:
        return jsonify({"error": "Request body required"}), 400

    def _get_field(name: str, required: bool = True) -> str:
        value = (payload.get(name) or "").strip()
        if required and not value:
            raise ValueError(f"{name} is required")
        return value

    try:
        username = _get_field("username")
        password = _get_field("password")
        full_name = _get_field("fullName")
        email = _get_field("email")
        display_name = (payload.get("displayName") or full_name).strip() or full_name
        role = (payload.get("role") or "viewer").strip().lower()
        is_active_raw = payload.get("isActive")
        if is_active_raw is None:
            is_active = True
        else:
            is_active = str(is_active_raw).strip().lower() not in {"0", "false", "no"}

        raw_device_ids: List[str] = []
        if isinstance(payload.get("deviceIds"), (list, tuple)):
            raw_device_ids = [str(item) for item in payload.get("deviceIds") if str(item).strip()]
        elif payload.get("deviceIds"):
            raw_device_ids = [str(payload.get("deviceIds"))]

        if not raw_device_ids and not request.is_json:
            raw_device_ids = [value for value in request.form.getlist("deviceIds") if value]

        device_ids = [int(value) for value in raw_device_ids]
        if not device_ids:
            raise ValueError("At least one deviceId must be provided")
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    allowed_roles = {"admin", "operator", "viewer"}
    if role not in allowed_roles:
        return jsonify({"error": f"role must be one of {sorted(allowed_roles)}"}), 400

    conn = get_connection()
    try:
        user_row = register_user_account(
            conn,
            username=username,
            password=password,
            full_name=full_name,
            display_name=display_name,
            email=email,
            role=role,
            is_active=is_active,
            device_ids=device_ids,
        )
        conn.commit()
    except ValueError as exc:
        conn.rollback()
        return jsonify({"error": str(exc)}), 400
    except mysql.connector.IntegrityError as exc:
        conn.rollback()
        return jsonify({"error": "Username or email already exists", "details": str(exc)}), 409
    except Exception as exc:
        conn.rollback()
        current_app.logger.exception("Failed to register user %s", username)
        return jsonify({"error": str(exc)}), 500

    if not user_row:
        return jsonify({"error": "Failed to load created user"}), 500

    return jsonify(
        {
            "user": _user_dict(user_row),
            "deviceIds": device_ids,
        }
    ), 201


@api_bp.route("/users/register/test", methods=["GET"])
def render_register_form() -> Response:
    """Serve a lightweight HTML form for manual register flow testing."""
    conn = get_connection()
    device_limit = current_app.config.get("REGISTER_FORM_DEVICE_LIMIT", 50)
    available_devices = list_unassigned_devices(conn, device_limit)

    if available_devices:
        option_rows = []
        for device in available_devices:
            label = device.get("device_name") or device.get("device_no") or f"Device {device['external_id']}"
            detail = f"#{device['external_id']}"
            option_rows.append(
                f'<option value="{escape(str(device["external_id"]))}">{escape(label)} ({escape(detail)})</option>'
            )
        devices_html = "\n".join(option_rows)
    else:
        devices_html = '<option value="" disabled>No unassigned devices available</option>'

    form_action = escape(current_app.config.get("REGISTER_FORM_POST_URL", "/api/users/register"))

    html = f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>Test Register Form</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 2rem; background: #f5f7fb; }}
        form {{ max-width: 420px; padding: 1.5rem; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(15,23,42,0.12); }}
        label {{ display: block; font-size: 0.9rem; margin-bottom: 0.35rem; color: #0f172a; }}
        input, select {{ width: 100%; padding: 0.55rem 0.65rem; margin-bottom: 0.9rem; border: 1px solid #cbd5f5; border-radius: 4px; }}
        button {{ background: #2563eb; color: #fff; border: none; padding: 0.65rem 1.2rem; border-radius: 4px; cursor: pointer; }}
        button:hover {{ background: #1e40af; }}
        .helper {{ font-size: 0.8rem; color: #475569; margin-bottom: 0.6rem; }}
    </style>
</head>
<body>
    <h2>Manual User Registration (Test)</h2>
    <form action=\"{form_action}\" method=\"post\">
        <label for=\"deviceIds\">Assign Devices</label>
        <div class=\"helper\">Select one or more unassigned TLINK devices to bind to this user.</div>
        <select id=\"deviceIds\" name=\"deviceIds\" multiple size=\"6\" required>
            {devices_html}
        </select>

        <label for=\"username\">Username</label>
        <input id=\"username\" name=\"username\" placeholder=\"admin\" required />

        <label for=\"fullName\">Full Name</label>
        <input id=\"fullName\" name=\"fullName\" placeholder=\"Jane Doe\" required />

        <label for=\"displayName\">Display Name</label>
        <input id=\"displayName\" name=\"displayName\" placeholder=\"Operations Team\" />

        <label for=\"email\">Email</label>
        <input id=\"email\" name=\"email\" type=\"email\" placeholder=\"user@example.com\" required />

        <label for=\"password\">Password</label>
        <input id=\"password\" name=\"password\" type=\"password\" required />

        <label for=\"role\">Role</label>
        <select id=\"role\" name=\"role\">
            <option value=\"viewer\">Viewer</option>
            <option value=\"operator\">Operator</option>
            <option value=\"admin\">Admin</option>
        </select>

        <button type=\"submit\">Register User</button>
    </form>
</body>
</html>"""

    return current_app.response_class(html, mimetype="text/html")


@api_bp.route("/reference/device-apis", methods=["GET"])
def list_device_reference() -> Response:
    """Lightweight digest of official device endpoints for quick discovery."""
    doc_path = Path(current_app.config.get("API_DOC_SOURCE", ""))
    doc_exists = doc_path.exists()

    reference = [
        {
            "endpoint": "/api/device/getDevices",
            "method": "GET",
            "summary": "Paginated list of devices filtered by status, alarms, and groups.",
            "keyFields": ["userId", "currPage", "pageSize"],
        },
        {
            "endpoint": "/api/device/getDeviceSensorDatas",
            "method": "GET",
            "summary": "Snapshot of every sensor attached to each device, including online state.",
            "keyFields": ["userId", "deviceId", "currPage", "pageSize"],
        },
        {
            "endpoint": "/api/device/getSingleDeviceDatas",
            "method": "GET",
            "summary": "Returns a single device with geolocation, warnings, and sensor inventory.",
            "keyFields": ["userId", "deviceId"],
        },
        {
            "endpoint": "/api/device/getSensorHistroy",
            "method": "GET",
            "summary": "Historical time series for one sensor with pagination and time bounds.",
            "keyFields": ["userId", "sensorId", "startTime", "endTime", "currPage"],
        },
    ]

    return jsonify(
        {
            "source": str(doc_path) if doc_exists else "official_api_reference.md not found",
            "count": len(reference),
            "reference": reference,
        }
    )


def _find_device(conn, device_external_id: int, owner_id: Optional[str]) -> Optional[dict]:
    if owner_id:
        rows = fetch_devices(conn, owner_id, device_external_id, 1, 0)
        if rows:
            return rows[0]
        return None
    return fetch_device_by_external_id(conn, device_external_id)


def _user_dict(row: dict) -> dict:
    return {
        "userId": row["id"],
        "username": row["username"],
        "parentUserId": row["parent_user_id"],
        "displayName": row["display_name"],
        "email": row["email"],
        "role": row["role"],
        "isActive": _row_bool(row["is_active"]),
    }


def _device_summary(row: dict) -> dict:
    return {
        "deviceId": row["external_id"],
        "parentUserId": row["parent_user_id"],
        "userId": row.get("user_id"),
        "lastFlag": row["last_flag"],
        "lastPushTime": normalize_timestamp(row["last_push_time"]),
    }


def _sensor_summary(row: dict, device_external_id: int) -> dict:
    return {
        "sensorId": row["external_id"],
        "deviceId": device_external_id,
        "sensorName": row.get("sensor_name"),
        "sensorTypeId": row["sensor_type_id"],
        "isAlarm": _row_bool(row["is_alarm"]),
        "isLine": _row_bool(row["is_line"]),
        "latestValue": row["latest_value"],
        "latestRecordedAt": normalize_timestamp(row["latest_recorded_at"]),
        "unit": row.get("unit"),
    }


def _log_entry_payload(entry: dict) -> dict:
    timestamp = entry.get("timestamp")
    timestamp_str = (
        timestamp.isoformat()
        if isinstance(timestamp, datetime)
        else normalize_timestamp(timestamp)
    )

    return {
        "timestamp": timestamp_str,
        "status": entry.get("status"),
        "httpStatus": entry.get("http_status"),
        "message": entry.get("message"),
        "sensors": [_log_sensor_payload(sensor) for sensor in entry.get("sensors", [])],
    }


def _log_sensor_payload(entry: dict) -> dict:
    sensor_id = entry.get("sensorId") or entry.get("sensor_id")
    try:
        sensor_id = int(sensor_id)
    except (TypeError, ValueError):
        pass

    return {
        "sensorId": sensor_id,
        "reading": entry.get("reading"),
        "units": entry.get("units"),
        "isAlarm": _row_bool(entry.get("isAlarm")),
        "isOnline": _row_bool(entry.get("isOnline")),
    }


def _row_bool(value: dict) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return bool(int(value))
    if isinstance(value, (int, float)):
        return bool(int(value))
    if isinstance(value, str):
        return value.strip() not in {"0", "false", "False", ""}
    return bool(value)


def _reading_dict(row: dict) -> dict:
    return {
        "recordedAt": normalize_timestamp(row["recorded_at"]),
        "sensorTimestamp": row["sensor_timestamp"],
        "isAlarm": _row_bool(row["is_alarm"]),
        "isLine": _row_bool(row["is_line"]),
        "rawValue": row["raw_value"],
        "value": row["scaled_value"],
    }

