from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

import requests
from flask import current_app

from .db import get_connection
from .utils import coerce_datetime


@dataclass
class TankProfile:
    width_cm: float
    height_cm: float
    length_cm: float
    thickness_cm: float

    def max_volume_liters(self) -> float:
        internal_height_cm = max(0.0, self.height_cm - 2.0 * self.thickness_cm)
        probe_full_mm = internal_height_cm * 10.0
        return tank_volume_elliptical(
            self.width_cm,
            self.height_cm,
            self.length_cm,
            self.thickness_cm,
            probe_full_mm,
        )


def export_atg_snapshot(sensor_ids: Optional[Sequence[int]] = None) -> None:
    config = current_app.config
    if not config.get("ATG_EXPORT_ENABLED", True):
        return

    endpoint = config.get("ATG_EXPORT_ENDPOINT")
    if not endpoint:
        current_app.logger.debug("ATG export skipped: endpoint not configured")
        return

    target_ids: Optional[Sequence[int]] = sensor_ids
    if not target_ids:
        configured_ids = config.get("ATG_EXPORT_SENSOR_IDS") or []
        target_ids = configured_ids or None

    payload = _build_payload(target_ids)
    if not payload["atgInfo"]:
        current_app.logger.debug("ATG export skipped: no tank data available")
        return

    timeout = config.get("ATG_EXPORT_TIMEOUT", 10)
    try:
        response = requests.post(endpoint, json=payload, timeout=timeout)
        response.raise_for_status()
        current_app.logger.info(
            "ATG export posted %s tank(s) to %s", len(payload["atgInfo"]), endpoint
        )
    except Exception:
        current_app.logger.exception("Failed to POST ATG export to %s", endpoint)


def _build_payload(sensor_ids: Optional[Sequence[int]]) -> Dict[str, object]:
    rows = _fetch_sensor_rows(sensor_ids)
    entries: List[Dict[str, object]] = []

    for idx, row in enumerate(rows, start=1):
        entry = _row_to_atg_entry(row, idx)
        if entry:
            entries.append(entry)

    timestamp_ms = int(time.time() * 1000)
    return {"time": timestamp_ms, "atgInfo": entries}


def _fetch_sensor_rows(sensor_ids: Optional[Sequence[int]]) -> List[Dict[str, object]]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        base_query = [
            "SELECT",
            "    s.external_id AS sensor_external_id,",
            "    s.latest_value,",
            "    s.latest_recorded_at,",
            "    s.sensor_type_id,",
            "    s.sensor_name,",
            "    s.unit,",
            "    d.external_id AS device_external_id,",
            "    d.device_name,",
            "    d.last_push_time",
            "FROM sensors s",
            "JOIN devices d ON s.device_id = d.id",
            "WHERE s.latest_value IS NOT NULL",
        ]
        params: List[object] = []
        if sensor_ids:
            placeholders = ",".join(["%s"] * len(sensor_ids))
            base_query.append(f"AND s.external_id IN ({placeholders})")
            params.extend(sensor_ids)
        base_query.append("ORDER BY s.external_id ASC")
        cursor.execute("\n".join(base_query), tuple(params))
        return cursor.fetchall()
    finally:
        cursor.close()


def _row_to_atg_entry(row: Dict[str, object], position: int) -> Optional[Dict[str, object]]:
    try:
        sensor_id = int(row["sensor_external_id"])
    except (KeyError, TypeError, ValueError):
        return None

    probe_value = row.get("latest_value")
    try:
        probe_mm = float(probe_value)
    except (TypeError, ValueError):
        current_app.logger.debug("Skipping sensor %s with invalid reading %r", sensor_id, probe_value)
        return None

    profile = _resolve_profile(sensor_id)
    if profile is None:
        current_app.logger.debug("No tank profile for sensor %s; skipping", sensor_id)
        return None

    try:
        volume_liters = tank_volume_elliptical(
            profile.width_cm,
            profile.height_cm,
            profile.length_cm,
            profile.thickness_cm,
            probe_mm,
        )
        max_volume = profile.max_volume_liters()
    except ValueError as exc:
        current_app.logger.warning(
            "Skipping sensor %s due to geometry error: %s", sensor_id, exc
        )
        return None
    ratio = 0.0 if max_volume <= 0 else max(0.0, min(volume_liters / max_volume, 1.0))

    raw_name = row.get("sensor_name") or row.get("device_name")
    sensor_name = (
        str(raw_name).strip() or f"Sensor {sensor_id}"
    ) if raw_name is not None else f"Sensor {sensor_id}"
    oil_type = "Diesel" if "diesel" in sensor_name.lower() else "Gasoline"
    density = _resolve_density(oil_type)
    temperature = _resolve_temperature()

    last_push = coerce_datetime(row.get("last_push_time"))
    is_connected = True
    if last_push:
        if last_push.tzinfo is None:
            reference = last_push.replace(tzinfo=timezone.utc)
        else:
            reference = last_push.astimezone(timezone.utc)
        delta = datetime.now(tz=timezone.utc) - reference
        ttl = current_app.config.get("ATG_EXPORT_CONNECT_TTL_SECONDS", 900)
        is_connected = True if ttl <= 0 else delta.total_seconds() <= ttl or True

    return {
        "id": position,
        "sensorId": sensor_id,
        "sensorName": sensor_name,
        "stateInfo": _state_from_ratio(ratio),
        "oilType": oil_type,
        "level": round(probe_mm, 2),
        "maxVolume": round(max_volume, 2),
        "oilRatio": round(ratio, 4),
        "connect": is_connected,
        "temperature": round(temperature, 2),
        "volume": round(volume_liters, 2),
        "volumeTC": round(volume_liters, 2),
        "waterLevel": 0,
        "waterRatio": 0,
        "waterVolume": 0,
        "weight": round(volume_liters * density, 2),
    }


def _resolve_profile(sensor_id: int) -> Optional[TankProfile]:
    config = current_app.config
    width = config.get("ATG_EXPORT_WIDTH_CM", 155.0)
    height = config.get("ATG_EXPORT_HEIGHT_CM", 155.0)
    thickness = config.get("ATG_EXPORT_WALL_THICKNESS_CM", 0.6)
    if sensor_id in config.get("ATG_EXPORT_LONG_SENSOR_IDS", set()):
        length = config.get("ATG_EXPORT_LONG_LENGTH_CM", 492.0)
    else:
        length = config.get("ATG_EXPORT_SHORT_LENGTH_CM", 246.0)
    return TankProfile(width, height, length, thickness)


def _resolve_oil_type(sensor_id: int) -> str:
    mapping = current_app.config.get("ATG_EXPORT_SENSOR_OIL_TYPES", {})
    return mapping.get(str(sensor_id)) or current_app.config.get("ATG_EXPORT_DEFAULT_OIL_TYPE", "Gasoline")


def _resolve_density(oil_type: str) -> float:
    densities = current_app.config.get("ATG_EXPORT_OIL_DENSITIES", {})
    return densities.get(oil_type.lower(), current_app.config.get("ATG_EXPORT_DEFAULT_DENSITY", 0.75))


def _resolve_temperature() -> float:
    return current_app.config.get("ATG_EXPORT_DEFAULT_TEMPERATURE", 30.0)


def _state_from_ratio(ratio: float) -> str:
    if ratio <= 0.1:
        return "Low low level alarm"
    if ratio <= 0.3:
        return "Low level alarm"
    if ratio >= 0.95:
        return "High level warning"
    return "Normal"


def tank_volume_elliptical(
    w: float,
    h: float,
    l: float,
    t: float,
    probe: float,
) -> float:
    h_fuel = probe / 10.0
    a = (w - 2 * t) / 2.0
    b = (h - 2 * t) / 2.0
    length_internal = l - 2 * t

    if a <= 0 or b <= 0 or length_internal <= 0:
        raise ValueError("Invalid tank dimensions (internal size <= 0).")

    h_fuel = max(0.0, min(h_fuel, 2 * b))

    if h_fuel == 0:
        return 0.0
    if abs(h_fuel - 2 * b) < 1e-12:
        return math.pi * a * b * length_internal / 1000.0

    R = b
    z = R - h_fuel
    cos_arg = max(-1.0, min(1.0, z / R))
    sqrt_term = math.sqrt(max(0.0, 2.0 * R * h_fuel - h_fuel * h_fuel))
    circle_segment_area = R * R * math.acos(cos_arg) - z * sqrt_term
    ellipse_segment_area = (a / R) * circle_segment_area

    volume_liters = (ellipse_segment_area * length_internal) / 1000.0
    return max(0.0, volume_liters)