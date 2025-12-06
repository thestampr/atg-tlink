# ATG/TLink Push Data Service

A Flask-based reference implementation that ingests TLINK push payloads, stores the readings in a MySQL database (with optional phpMyAdmin dashboard), and exposes convenience APIs for device history. The service mirrors the workflows captured inside `docs/push_data_protocol.md` and `docs/official_api_reference.md` so you can test integrations locally before pointing the TLINK platform at your public endpoint.

## Features

- **Webhook ingestion** (`POST /api/webhooks/tlink`): stores every `sensorsDates` entry (including the vendor-supplied `sensorName`), maintains user → device bindings, and keeps the latest values per sensor.
- **Device history service** (`GET /api/devices`): paginated device list with optional `ownerId` filtering plus per-sensor history windows (`deviceId`, `startTime`, `endTime`, `historyLimit`).
- **Latest snapshot API** (`GET /api/devices/<deviceId>/latest`): mirrors the "single device" view from the official API reference using your locally persisted data.
- **ATG export bridge**: after each TLINK sync cycle, recalculates tank volumes from probe readings (supports the supplied elliptical-tank math) and POSTs the result (now tagged with `sensorId` + `sensorName`) to `https://supsopha.com/api/upload_atg_record.php`.
- **Device reference helper** (`GET /api/reference/device-apis`): quick reminders for the most common device APIs described in `docs/official_api_reference.md` so frontend teams know how this local service relates to the vendor endpoints.
- **Remote sync background task**: polls TLINK's `/api/device/getDeviceSensorDatas` on a 60-second cadence (configurable), using the OAuth client to stay authenticated and writing the response through the same ingestion pipeline as the webhook.
- **Per-device sync logs + retention**: every device sync produces a structured log line (one file per device per day) that lists all sensors captured, and a 12-hour maintenance task prunes log files older than `LOG_AGE` days (default 90).
- **CORS enabled** for `/api/*` with an allow-list sourced from `.env`.
- **MySQL schema + phpMyAdmin**: `sql/schema.sql` auto-imports into MySQL (both on Flask startup and via Docker), and `docker-compose.yml` ships with phpMyAdmin for quick inspections.

## Project Layout

```
app.py                 # Flask entry point
app/
   __init__.py          # Application factory + CORS wiring
   config.py            # Environment-driven settings
   db.py                # MySQL connection pooling + query helpers
   routes.py            # All API endpoints
   utils.py             # Webhook signature + datetime helpers
docker/
   entrypoint.sh        # Container entrypoint wrapper used by the API image
.dockerignore          # Build context exclusions
Dockerfile             # Container image definition
docker-compose.yml     # 1-command local stack with persistent volume
sql/schema.sql         # DDL for stand-alone DB provisioning
.env                   # Runtime configuration (never commit secrets!)
.env.example           # Template to share with other developers
requirements.txt       # Python dependencies
```

## Prerequisites

- Python 3.11+ (tested up to 3.13 without extra shims)
- MySQL 8.x (install locally or rely on the included Docker Compose stack)

## Setup

1. **Create & activate a virtual environment**
   ```cmd
   py -3 -m venv .venv
   .venv\Scripts\activate
   ```
2. **Install dependencies**
   ```cmd
   pip install -r requirements.txt
   ```
3. **Configure environment**
   - Copy `.env.example` to `.env` (already present with safe defaults).
   - Update `DATABASE_URL`, `SECRET_KEY`, and `PUSH_WEBHOOK_SECRET` (used for optional HMAC validation via the `X-TLink-Signature` header).
   - Tune sync logging with `LOG_AGE` (retention window in days) and `SYNC_LOG_DIR` (destination folder for `logs/<deviceId>/device<deviceId>-YYYY-MM-DD.log`).
4. **Apply the schema** (optional; the app can run it automatically when `AUTO_APPLY_SCHEMA=true`)
   ```cmd
   mysql -h localhost -u root -p tlink < sql/schema.sql
   ```
5. **Run the service over HTTPS**
   ```cmd
   python app.py
   ```
   The entry point now enables TLS by default. On first launch it will drop a self-signed dev certificate inside `instance/certs`. Trust the generated `localhost.crt` (or point `SSL_CERT_FILE` / `SSL_KEY_FILE` at your own cert pair) before calling `https://localhost:5000` to avoid browser warnings. Set `USE_HTTPS=false` if you need to quickly revert to HTTP for debugging proxies or tooling.

## Running with Docker

1. **Copy and tweak environment** (if you have not already)
   ```cmd
   copy .env.example .env
   ```
   For containers we recommend pointing `DATABASE_URL` to `/data/tlink.db` (the default override in `docker-compose.yml` already does this).
2. **Start via Docker Compose**
   ```cmd
   docker compose up --build
   ```
   - Exposes the API on `https://localhost:5000` (self-signed certificate stored under `/app/instance/certs`).
   - Launches a MySQL 8.4 container that auto-imports `sql/schema.sql` on first boot and persists data inside the `mysql_data` volume.
   - Adds phpMyAdmin on `http://localhost:8080` (use the credentials from `.env`) for visual management.
3. **Alternative: standalone Docker commands**
   ```cmd
   docker build -t atg-tlink-api .
   docker run --rm -p 5000:5000 --env-file .env \
     -e DATABASE_URL=mysql://tlink:tlinkpass@host.docker.internal:3306/tlink atg-tlink-api
   ```
4. **Stopping and cleaning**
   ```cmd
   docker compose down        # stops containers but keeps the volume
   docker volume rm mysql_data  # optional, removes persisted readings
   ```


## Local HTTPS & Certificates

- Running `python app.py` (or the Docker container) always starts the Flask server with TLS enabled. By default the app lazily generates a self-signed certificate at `instance/certs/localhost.crt` and reuses it on subsequent boots.
- Override the certificate/key locations with `.env` entries:
   - `SSL_CERT_FILE`, `SSL_KEY_FILE` → point to an existing pair (relative paths resolve from the project root).
   - `SSL_AUTO_GENERATE` (default `true`) → switch to `false` to skip auto-generation. When disabled and the files are missing, the server falls back to HTTP.
- Control whether HTTPS is used at all with `USE_HTTPS` (default `true`). When set to `false`, the server skips TLS entirely but still honors `PORT`/host settings.
- Trust the generated certificate in your OS/browser or pass `-k/--insecure` to tools like `curl` while developing locally.
- In Docker, mount your own certificate directory and update the env vars accordingly if you need to test with a CA-signed cert.


## TLINK Cloud Sync

- A background job named `tlink_device_sync` runs every `TLINK_SYNC_INTERVAL_SECONDS` seconds (default `60`) whenever `TLINK_SYNC_ENABLED=true`. Each run targets the configured `TLINK_ACCOUNT_NUMBER`, calls TLINK's `/api/device/getDeviceSensorDatas`, and feeds the response through the same ingestion pipeline as the webhook.
- Key environment settings:
   - Core API routing: `TLINK_BASE_URL`, `TLINK_HTTP_TIMEOUT`, `TLINK_APP_ID` (the sensor endpoint and method are fixed to TLINK defaults).
   - OAuth password-grant credentials: `TLINK_OAUTH_TOKEN_URL`, `TLINK_OAUTH_CLIENT_ID`, `TLINK_OAUTH_CLIENT_SECRET`, `TLINK_OAUTH_USERNAME`, `TLINK_OAUTH_PASSWORD`, optional `TLINK_OAUTH_SCOPE`, and `TLINK_OAUTH_REFRESH_BUFFER` (seconds before expiry to refresh).
   - Scheduler controls: `TLINK_SYNC_ENABLED`, `TLINK_SYNC_INTERVAL_SECONDS`, and `TLINK_SYNC_PAGE_SIZE`.
- Tokens are cached and refreshed automatically—no need to paste short-lived bearer strings into `.env`.
- Watch the Flask logs for `TLINK sync completed...` messages to confirm the job is running, or set `TLINK_SYNC_ENABLED=false` to disable the background pull entirely.

## ATG Export Bridge

- After every successful TLINK sync cycle the service collects the latest probe readings for the configured level sensors, converts millimeters to liters with the supplied elliptical-tank math, forces the water fields to zero, and POSTs `{ "time": <epoch_ms>, "atgInfo": [...] }` to `ATG_EXPORT_ENDPOINT` (default `https://supsopha.com/api/upload_atg_record.php`). Each `atgInfo` entry now includes both `sensorId` and the persisted `sensorName` for downstream labeling.
- Tank geometry defaults: `ATG_EXPORT_WIDTH_CM=155`, `ATG_EXPORT_HEIGHT_CM=155`, `ATG_EXPORT_WALL_THICKNESS_CM=0.6`. Sensors listed in `ATG_EXPORT_LONG_SENSOR_IDS` (default `6026176`) use `ATG_EXPORT_LONG_LENGTH_CM=492`, while all remaining sensors use `ATG_EXPORT_SHORT_LENGTH_CM=246`.
- Oil metadata and densities come from `ATG_EXPORT_SENSOR_OIL_TYPES`, `ATG_EXPORT_DEFAULT_OIL_TYPE`, `ATG_EXPORT_DEFAULT_DENSITY`, and `ATG_EXPORT_OIL_DENSITIES` (e.g., `6026176:Diesel` plus `Diesel:0.84,Gasoline:0.75`). These values drive the `oilType`, `oilRatio`, and `weight` fields in the outbound payload.
- Use `ATG_EXPORT_SENSOR_IDS` to limit which sensors are exported (leave blank to include every sensor with a numeric reading). Device connectivity is inferred from `last_push_time` and the `ATG_EXPORT_CONNECT_TTL_SECONDS` sliding window (default 15 minutes).
- Additional controls include `ATG_EXPORT_ENABLED`, `ATG_EXPORT_TIMEOUT`, and `ATG_EXPORT_DEFAULT_TEMPERATURE` (a fallback since TLINK does not supply a temperature sensor reading here).


## API Contracts

**General conventions**

- Every REST path is rooted at `/api`. JSON responses include `error` keys on failures; `GET /api/users/register/test` is the only HTML endpoint.
- `ownerId` query parameters refer to the local UUID stored in `users.id`; skip them to operate on the full device inventory. `deviceId`/`sensorId` remain the TLINK integers (`devices.external_id` and `sensors.external_id`).
- Timestamp filters accept `YYYY-MM-DD HH:MM:SS` strings and are normalized before querying MySQL/log files.
- When provided, `X-TLink-Signature` must be `sha256=...` HMAC over the raw request body using `PUSH_WEBHOOK_SECRET`.

### Webhook ingestion — `POST /api/webhooks/tlink`

**Purpose:** Entry point for TLINK push notifications documented in `docs/push_data_protocol.md`.

**Headers**

| Header | Required | Notes |
| --- | --- | --- |
| `Content-Type: application/json` | yes | Body must be JSON.
| `X-TLink-Signature` | yes when `PUSH_WEBHOOK_SECRET` is set | `sha256=<hex>` HMAC calculated over the raw payload. Requests without or with an invalid signature return `401`.

**Body highlights**

| Field | Description |
| --- | --- |
| `deviceId` / `deviceUserid` / `parentUserId` | Used to find the local device and owning user.
| `flag`, `rawData`, `pushTime` | Persisted onto the device row for debugging.
| `sensorsDates[]` | Each entry must supply `sensorsId`, `sensorTypeId`, `isLine`, `isAlarm`, `unit`, `recordedAt`, and `value`. They are upserted into `sensors` plus `sensor_readings`.

**Behavior**

- The raw body is validated, signature checked, then passed to `process_push_payload`, which deduplicates sensor readings via `(sensor_id, recorded_at, sensor_timestamp)`.
- Each sensor update refreshes both the sensor table and its owning device’s last push metadata.

**Responses**

- `200 {"status":"ok","storedReadings":<int>}` on success.
- `400` for missing/invalid JSON or bad field contents, `401` for signature mismatch.

### Device directory — `GET /api/devices`

**Purpose:** Paginated inventory of all known devices along with recent readings per sensor. Use the optional `ownerId` to scope the response to a single local user.

**Query parameters**

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `ownerId` | string (UUID) | none | Filters devices to those assigned to the specified local user. When present, the response includes a `user` block; otherwise it returns the global inventory.
| `deviceId` | int | — | Limits the result set to one TLINK device ID.
| `startTime` / `endTime` | string | none | Bounds applied before querying MySQL history tables.
| `page` | int | `1` | 1-indexed; clamped to `>=1`.
| `pageSize` | int | `DEFAULT_PAGE_SIZE` | Capped at `MAX_PAGE_SIZE`.
| `historyLimit` | int | `HISTORY_LIMIT` | Max readings per sensor (minimum `1`).

**Response shape**

- `user`: present only when `ownerId` is supplied; contains normalized user info (`userId`, `username`, `displayName`, etc.).
- `pagination`: `page`, `pageSize`, `total`, `pages`.
- `devices[]`: each entry includes `_device_summary` (deviceId, userId, lastFlag/lastPushTime) plus `sensors[]`. Every sensor ships `_sensor_summary` fields (now including `sensorName`) and a `history` array of up to `historyLimit` readings.

**Errors:** `404` when `ownerId` is provided but the user does not exist; `400` when query parameters fail validation.

### Device snapshot — `GET /api/devices/<deviceId>/latest`

**Purpose:** Quickly fetches the last known value for every sensor on a single device.

- Optional `ownerId` query parameter enforces that the device belongs to a specific local user before returning data.
- Returns `{ "device": { ... }, "sensors": [{ ... , "latest": { ... } }] }` where each sensor carries `sensorName` and `latest` mirrors `_reading_dict` (`recordedAt`, `sensorTimestamp`, `isAlarm`, `isLine`, `rawValue`, `value`).
- `404` is returned if the device (or the owner/device combination) does not exist.

### File-backed history — `GET /api/devices/<deviceId>/history`

**Purpose:** Replay the exact payloads fetched by the sync worker using log files under `logs/<deviceId>/device<deviceId>-YYYY-MM-DD.log`. Accepts the same optional `ownerId` filter as the other device endpoints.

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `startTime` / `endTime` | string | none | Filters applied while reading log entries before truncation.
| `historyLimit` | int | `HISTORY_LIMIT` | Caps the number of log entries returned per sensor.

**Response:**

- `device`: `_device_summary` payload; `user` is included when `ownerId` is supplied.
- `sensors[]`: for known database sensors, includes `_sensor_summary` and `history` pulled from the logs. Unknown-but-logged sensor IDs still appear with `sensorTypeId`, `unit`, etc. set to `null` so nothing is silently hidden.

### Sync log browser — `GET /api/logs/<deviceId>` (optional `/ <sensorId>`)

**Purpose:** Inspect structured sync logs produced by the TLINK polling worker, optionally enforcing device ownership via `ownerId`.

**Query parameters**

| Parameter | Type | Notes |
| --- | --- | --- |
| `ownerId` | string (UUID) | When provided, the API verifies the device belongs to the supplied user before returning logs.
| `startTime` / `endTime` | string | Restricts log search window.
| `status` | string | Case-insensitive filter for entries tagged `success`, `error`, etc.
| `page` / `pageSize` | int | Server-side pagination; size clamped between `1` and `MAX_PAGE_SIZE`.

**Response:**

- `logs[]`: entries with `timestamp`, `status`, `httpStatus`, `message`, and nested `sensors[]` (sensorId, reading, units, isAlarm, isOnline).
- `pagination`: echoes the paging inputs plus `returned` and `hasMore`.
- Requires `TLINK_ACCOUNT_NUMBER` to be configured; otherwise the endpoint responds with `500`.

### Manual registration API — `POST /api/users/register`

**Purpose:** Create a local user account and bind one or more unassigned devices in a single transaction. Accepts JSON or `application/x-www-form-urlencoded` bodies.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `username` | string | yes | Must be unique; conflicts raise `409`.
| `password` | string | yes | Stored as a Werkzeug salted hash.
| `fullName` | string | yes | Used as a fallback for `displayName`.
| `displayName` | string | no | Defaults to `fullName` if omitted/blank.
| `email` | string | yes | Must be unique.
| `role` | string | no | One of `admin`, `operator`, `viewer` (default `viewer`).
| `isActive` | bool/string | no | Truthy strings keep the account active (default `true`).
| `deviceIds` | array or repeated form field | yes | List of TLINK device IDs to assign. Device must exist and not be linked to another user.

**Responses:** `201` with `{ "user": { ... }, "deviceIds": [...] }` on success; `400` for validation errors, `409` for username/email collisions, `500` for unexpected failures (with server logs capturing the trace).

### Manual registration form — `GET /api/users/register/test`

- Returns a lightweight HTML page that posts to `/api/users/register`. The dropdown is populated with `list_unassigned_devices()` (cap controlled by `REGISTER_FORM_DEVICE_LIMIT`).
- Useful for smoke-testing end-to-end registration without crafting JSON by hand. Customize the `action` attribute through `REGISTER_FORM_POST_URL`.

### Device reference helper — `GET /api/reference/device-apis`

- Surfaces a curated subset of endpoints from `docs/official_api_reference.md`, making it easy for frontend developers to navigate between this emulator and TLINK’s SaaS API.
- Response payload: `{ "source": <path or fallback>, "count": 4, "reference": [ {"endpoint": ..., "method": ..., "summary": ..., "keyFields": [...]}, ... ] }`.

## Database Schema Overview

| Table | Description |
| --- | --- |
| `users` | Represents TLINK `deviceUserid` / `userId` owners. Internal primary key is a UUID (`CHAR(36)`) generated automatically. |
| `devices` | `deviceId` entities bound to a `user_id` (UUID FK). Stores the last push metadata plus descriptive fields such as `device_name`, `device_no`, `group_id`, lat/lng, `product_id`, `product_type`, and `protocol_label`. |
| `sensors` | Unique per `(device, sensorsId)` pairing. Tracks last-known status along with the vendor-reported `unit` and now persists `sensor_name` for labeling. |
| `sensor_readings` | Historical values captured for every push, deduplicated via `(sensor_id, recorded_at, sensor_timestamp)`. |

Use `sql/schema.sql` if you prefer applying DDL manually or when reseeding a fresh database. The runtime automatically executes this script at startup when `AUTO_APPLY_SCHEMA=true`, and the Docker MySQL container imports it on first initialization.

> **Upgrading note:** recent releases switched the `users.id` column (and dependent `devices.user_id` foreign key) to UUIDs so each tenant can be merged across environments without sequence collisions. If you have an existing database created before this change, run an `ALTER TABLE` to convert those columns to `CHAR(36)` (and backfill values with `UUID()` or your own keys) before restarting the app.

## Extending the Service

- Point `DATABASE_URL` at any reachable MySQL instance (cloud RDS, on-prem, etc.).
- Wire a background worker to forward processed readings to `/api/device/sendDataPoint` or control devices using `/api/device/switcherController` as documented in `docs/official_api_reference.md`.
- Add authentication (JWT/api keys) for the history endpoints before exposing them publicly.

## Testing the Webhook

Send the sample payload from `docs/push_data_protocol.md` (add `-k` unless you have trusted the certificate):

```cmd
curl -k -X POST https://127.0.0.1:5000/api/webhooks/tlink \
   -H "Content-Type: application/json" \
   -d @docs/sample_push.json
```

Provide `X-TLink-Signature` if `PUSH_WEBHOOK_SECRET` is set:

```cmd
$body = Get-Content docs\sample_push.json -Raw
$secret = "your-secret"
$signature = "sha256=$(echo -n $body | openssl dgst -sha256 -hmac $secret | awk '{print $2}')"
curl -k -X POST ... -H "X-TLink-Signature: $signature" ...
```

## Notes

- The service intentionally accepts the same timestamp formats the vendor emits (`YYYY-MM-DD HH:MM:SS`).
- GET endpoints stream JSON bodies similar to TLINK but follow HTTP conventions (query params only) to keep Swagger/OpenAPI generation straightforward.
- When TLINK retries the webhook, duplicate readings are ignored thanks to the unique constraint on `(sensor_id, recorded_at, sensor_timestamp)`.

Refer to the original PDFs mirrored inside `docs/` for exhaustive field descriptions while extending this codebase.
