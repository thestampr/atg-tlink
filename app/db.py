from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4
from urllib.parse import urlparse

import mysql.connector
from flask import current_app, g
from werkzeug.security import generate_password_hash

Connection = mysql.connector.MySQLConnection

_pool: Optional[mysql.connector.pooling.MySQLConnectionPool] = None


def init_app(app) -> None:
    settings = _parse_mysql_url(app.config["DATABASE_URL"])
    pool_size = app.config.get("DB_POOL_SIZE", 5)

    global _pool
    _pool = mysql.connector.pooling.MySQLConnectionPool(
        pool_name="tlink_pool", pool_size=pool_size, **settings
    )

    if app.config.get("AUTO_APPLY_SCHEMA", True):
        schema_path = Path(app.config["SCHEMA_PATH"])
        if schema_path.exists():
            conn = _pool.get_connection()
            try:
                _apply_schema(conn, schema_path)
            finally:
                conn.close()

    app.teardown_appcontext(close_connection)


def _parse_mysql_url(url: str) -> Dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"mysql", "mysql+mysqlconnector"}:
        raise ValueError("DATABASE_URL must use the mysql scheme")

    database = parsed.path.lstrip("/")
    if not database:
        raise ValueError("DATABASE_URL must include a database name")

    return {
        "user": parsed.username or "root",
        "password": parsed.password or "",
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "database": database,
        "auth_plugin": "mysql_native_password",
    }


def _apply_schema(conn: Connection, schema_path: Path) -> None:
    with open(schema_path, "r", encoding="utf-8") as ddl:
        sql_text = ddl.read()

    statements = [stmt.strip() for stmt in sql_text.split(";") if stmt.strip()]
    cursor = conn.cursor()
    try:
        for statement in statements:
            cursor.execute(statement)
        conn.commit()
    finally:
        cursor.close()


def get_connection() -> Connection:
    if "db" not in g:
        if _pool is None:
            raise RuntimeError("Database pool has not been initialized")
        conn = _pool.get_connection()
        conn.autocommit = False
        g.db = conn
    return g.db


def close_connection(_: Any = None) -> None:
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def register_user_account(
    conn: Connection,
    *,
    username: str,
    password: str,
    full_name: str,
    display_name: Optional[str],
    email: str,
    role: str,
    is_active: bool = True,
    device_ids: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    cursor = conn.cursor(dictionary=True)
    hashed = generate_password_hash(password)
    safe_display = display_name or full_name
    user_id = str(uuid4())
    try:
        cursor.execute(
            """
            INSERT INTO users (
                id,
                parent_user_id,
                username,
                password_hash,
                full_name,
                display_name,
                email,
                role,
                is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                None,
                username,
                hashed,
                full_name,
                safe_display,
                email,
                role,
                1 if is_active else 0,
            ),
        )
    finally:
        cursor.close()

    if device_ids:
        assign_devices_to_user(conn, user_id, device_ids)

    return fetch_user_by_id(conn, user_id)


def fetch_user_by_id(conn: Connection, user_id: str) -> Optional[Dict[str, Any]]:
    return _fetchone(conn, "SELECT * FROM users WHERE id = %s", (user_id,))


def fetch_device_by_external_id(conn: Connection, device_external_id: int) -> Optional[Dict[str, Any]]:
    return _fetchone(
        conn,
        "SELECT * FROM devices WHERE external_id = %s",
        (device_external_id,),
    )


def list_unassigned_devices(conn: Connection, limit: int = 50) -> List[Dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 1), 200))
    return _fetchall(
        conn,
        """
        SELECT external_id, device_name, device_no, group_id, user_id
        FROM devices
        WHERE user_id IS NULL
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        (safe_limit,),
    )


def assign_devices_to_user(
    conn: Connection, user_id: str, device_ids: Sequence[int]
) -> None:
    ids = [int(device_id) for device_id in device_ids]
    if not ids:
        return

    placeholders = ",".join(["%s"] * len(ids))
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            f"SELECT external_id, user_id FROM devices WHERE external_id IN ({placeholders})",
            tuple(ids),
        )
        rows = cursor.fetchall()
        if len(rows) != len(ids):
            missing = sorted(set(ids) - {row["external_id"] for row in rows})
            raise ValueError(f"Unknown device IDs: {missing}")

        conflicts = [row["external_id"] for row in rows if row["user_id"] and row["user_id"] != user_id]
        if conflicts:
            raise ValueError(f"Devices already assigned to another user: {conflicts}")

        params: List[Any] = [user_id]
        params.extend(ids)
        cursor.execute(
            f"UPDATE devices SET user_id = %s WHERE external_id IN ({placeholders})",
            tuple(params),
        )
    finally:
        cursor.close()


def upsert_device(
    conn: Connection,
    user_id: Optional[str],
    external_id: int,
    parent_user_id: str | None,
    device_name: str | None,
    device_no: str | None,
    group_id: int | None,
    lat: str | None,
    lng: str | None,
    product_id: str | None,
    product_type: str | None,
    protocol_label: str | None,
    flag: str | None,
    raw_payload: str | None,
    push_time: str | None,
) -> Dict[str, Any]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            INSERT INTO devices (
                external_id, parent_user_id, user_id,
                device_name, device_no, group_id, lat, lng,
                product_id, product_type, protocol_label,
                last_flag, last_raw_payload, last_push_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                parent_user_id = COALESCE(VALUES(parent_user_id), parent_user_id),
                user_id = COALESCE(VALUES(user_id), user_id),
                device_name = COALESCE(VALUES(device_name), device_name),
                device_no = COALESCE(VALUES(device_no), device_no),
                group_id = COALESCE(VALUES(group_id), group_id),
                lat = COALESCE(VALUES(lat), lat),
                lng = COALESCE(VALUES(lng), lng),
                product_id = COALESCE(VALUES(product_id), product_id),
                product_type = COALESCE(VALUES(product_type), product_type),
                protocol_label = COALESCE(VALUES(protocol_label), protocol_label),
                last_flag = COALESCE(VALUES(last_flag), last_flag),
                last_raw_payload = COALESCE(VALUES(last_raw_payload), last_raw_payload),
                last_push_time = COALESCE(VALUES(last_push_time), last_push_time),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                external_id,
                parent_user_id,
                user_id,
                device_name,
                device_no,
                group_id,
                lat,
                lng,
                product_id,
                product_type,
                protocol_label,
                flag,
                raw_payload,
                push_time,
            ),
        )
    finally:
        cursor.close()
    return _fetchone(
        conn,
        "SELECT * FROM devices WHERE external_id = %s",
        (external_id,),
    )


def upsert_sensor(
    conn: Connection,
    device_id: int,
    external_id: int,
    sensor_type_id: int | None,
    sensor_name: str | None,
    is_line: bool | None,
    is_alarm: bool | None,
    unit: str | None,
    latest_value: str | None,
    recorded_at: str | None,
) -> Dict[str, Any]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            """
            INSERT INTO sensors (
                external_id, device_id, sensor_type_id, sensor_name,
                is_line, is_alarm, unit, latest_value, latest_recorded_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                sensor_type_id = COALESCE(VALUES(sensor_type_id), sensor_type_id),
                sensor_name = COALESCE(VALUES(sensor_name), sensor_name),
                is_line = COALESCE(VALUES(is_line), is_line),
                is_alarm = COALESCE(VALUES(is_alarm), is_alarm),
                unit = COALESCE(VALUES(unit), unit),
                latest_value = COALESCE(VALUES(latest_value), latest_value),
                latest_recorded_at = COALESCE(VALUES(latest_recorded_at), latest_recorded_at),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                external_id,
                device_id,
                sensor_type_id,
                sensor_name,
                _to_bit(is_line),
                _to_bit(is_alarm),
                unit,
                latest_value,
                recorded_at,
            ),
        )
    finally:
        cursor.close()
    return _fetchone(
        conn,
        "SELECT * FROM sensors WHERE device_id = %s AND external_id = %s",
        (device_id, external_id),
    )


def insert_reading(
    conn: Connection,
    sensor_id: int,
    recorded_at: str,
    sensor_timestamp: str | None,
    is_alarm: bool | None,
    is_line: bool | None,
    raw_value: str | None,
    scaled_value: str | None,
    raw_payload: str | None,
) -> None:
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            INSERT IGNORE INTO sensor_readings (
                sensor_id, recorded_at, sensor_timestamp, is_alarm, is_line,
                raw_value, scaled_value, raw_payload
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                sensor_id,
                recorded_at,
                sensor_timestamp,
                _to_bit(is_alarm),
                _to_bit(is_line),
                raw_value,
                scaled_value,
                raw_payload,
            ),
        )
    finally:
        cursor.close()


def count_devices(conn: Connection, user_id: Optional[str], device_filter: int | None) -> int:
    clauses = []
    params: List[Any] = []
    if user_id:
        clauses.append("user_id = %s")
        params.append(user_id)
    if device_filter is not None:
        clauses.append("external_id = %s")
        params.append(device_filter)

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    row = _fetchone(
        conn,
        f"SELECT COUNT(*) AS c FROM devices{where_sql}",
        tuple(params),
    )
    return int(row["c"]) if row else 0


def fetch_devices(
    conn: Connection,
    user_id: Optional[str],
    device_filter: int | None,
    limit: int,
    offset: int,
) -> List[Dict[str, Any]]:
    clauses = []
    params: List[Any] = []
    if user_id:
        clauses.append("user_id = %s")
        params.append(user_id)
    if device_filter is not None:
        clauses.append("external_id = %s")
        params.append(device_filter)

    where_sql = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT * FROM devices
        {where_sql}
        ORDER BY external_id ASC
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    return _fetchall(conn, query, tuple(params))


def fetch_sensors(conn: Connection, device_id: int) -> List[Dict[str, Any]]:
    return _fetchall(
        conn,
        "SELECT * FROM sensors WHERE device_id = %s ORDER BY external_id ASC",
        (device_id,),
    )


def fetch_sensor_history(
    conn: Connection,
    sensor_id: int,
    start_time: str | None,
    end_time: str | None,
    limit: int,
) -> List[Dict[str, Any]]:
    clauses = ["sensor_id = %s"]
    params: List[Any] = [sensor_id]
    if start_time:
        clauses.append("recorded_at >= %s")
        params.append(start_time)
    if end_time:
        clauses.append("recorded_at <= %s")
        params.append(end_time)

    where_sql = " AND ".join(clauses)
    params.append(limit)
    query = f"""
        SELECT * FROM sensor_readings
        WHERE {where_sql}
        ORDER BY recorded_at DESC
        LIMIT %s
    """
    return _fetchall(conn, query, params)


def fetch_latest_sensor_reading(
    conn: Connection, sensor_id: int
) -> Optional[Dict[str, Any]]:
    return _fetchone(
        conn,
        """
        SELECT * FROM sensor_readings
        WHERE sensor_id = %s
        ORDER BY recorded_at DESC
        LIMIT 1
        """,
        (sensor_id,),
    )


def _to_bit(value: Optional[bool]) -> Optional[int]:
    if value is None:
        return None
    return int(bool(value))


def _fetchone(conn: Connection, query: str, params: Sequence[Any]) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params)
        return cursor.fetchone()
    finally:
        cursor.close()


def _fetchall(conn: Connection, query: str, params: Sequence[Any]) -> List[Dict[str, Any]]:
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(query, params)
        return cursor.fetchall()
    finally:
        cursor.close()