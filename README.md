# ATG/TLink Push Data Service

A Flask-based reference implementation that ingests TLINK push payloads, stores the readings in a MySQL database (with optional phpMyAdmin dashboard), and exposes convenience APIs for device history. The service mirrors the workflows captured inside `docs/push_data_protocol.md` and `docs/official_api_reference.md` so you can test integrations locally before pointing the TLINK platform at your public endpoint.

## Features

- **Webhook ingestion** (`POST /api/webhooks/tlink`): stores every `sensorsDates` entry, maintains user → device bindings, and keeps the latest values per sensor.
- **Device history service** (`GET /api/users/<userId>/devices`): paginated device list for a TLINK user with filters for `deviceId`, `startTime`, `endTime`, and `historyLimit` per sensor.
- **Latest snapshot API** (`GET /api/users/<userId>/devices/<deviceId>/latest`): mirrors the "single device" view from the official API reference using your locally persisted data.
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

- A background job named `tlink_device_sync` runs every `TLINK_SYNC_INTERVAL_SECONDS` seconds (default `60`) whenever `TLINK_SYNC_ENABLED=true`. Each run iterates over the comma-separated `TLINK_SYNC_USER_IDS`, calls TLINK's `/api/device/getDeviceSensorDatas`, and feeds the response through the same ingestion pipeline as the webhook.
- Key environment settings:
   - Core API routing: `TLINK_BASE_URL`, `TLINK_SENSOR_DATA_PATH`, `TLINK_SENSOR_HTTP_METHOD`, `TLINK_HTTP_TIMEOUT`, `TLINK_APP_ID`.
   - OAuth password-grant credentials: `TLINK_OAUTH_TOKEN_URL`, `TLINK_OAUTH_CLIENT_ID`, `TLINK_OAUTH_CLIENT_SECRET`, `TLINK_OAUTH_USERNAME`, `TLINK_OAUTH_PASSWORD`, optional `TLINK_OAUTH_SCOPE`, and `TLINK_OAUTH_REFRESH_BUFFER` (seconds before expiry to refresh).
   - Scheduler controls: `TLINK_SYNC_ENABLED`, `TLINK_SYNC_INTERVAL_SECONDS`, `TLINK_SYNC_PAGE_SIZE`, and `TLINK_SYNC_USER_IDS` (comma-separated TLINK `userId` values, e.g., `121025,385`).
- Tokens are cached and refreshed automatically—no need to paste short-lived bearer strings into `.env`.
- Watch the Flask logs for `TLINK sync completed...` messages to confirm the job is running, or set `TLINK_SYNC_ENABLED=false` to disable the background pull entirely.


## API Contracts

### 1. `POST /api/webhooks/tlink`
- **Purpose:** Receive push payloads documented in `docs/push_data_protocol.md`.
- **Headers:** Optional `X-TLink-Signature` (HMAC SHA-256 over the raw body) if `PUSH_WEBHOOK_SECRET` is configured.
- **Body:** Same JSON structure as the vendor PDF (`flag`, `deviceId`, `deviceUserid`, `parentUserId`, `sensorsDates`, `rawData`, etc.).
- **Response:** `{ "status": "ok", "storedReadings": <count> }`

### 2. `GET /api/users/<userId>/devices`
- **Query parameters:**
  - `deviceId` (int, optional)
  - `startTime`, `endTime` (`YYYY-MM-DD HH:MM:SS`, optional)
  - `page`, `pageSize` (defaults provided by `.env`)
  - `historyLimit` (max number of readings per sensor, defaults to `DEFAULT_HISTORY_LIMIT`)
- **Response:** User metadata plus a paginated `devices` array. Each device includes sensor summaries and recent history that mirrors `/api/device/getSensorHistroy` semantics from the official API reference.

### 3. `GET /api/users/<userId>/devices/<deviceId>/latest`
- **Purpose:** Quick snapshot of the latest stored values for every sensor on a device.
- **Response:** Device summary plus `sensors` array where each entry contains `latest` reading metadata.

### 4. `GET /api/users/<userId>/devices/<deviceId>/history`
- **Purpose:** Detailed sensor history for a specific device filtered by optional `startTime`, `endTime`, and `historyLimit` query parameters (defaults mirror the list endpoint).
- **Response:** User + device metadata plus each sensor's summary and capped history list. Sensor history is parsed directly from the per-device log files (`logs/<deviceId>/device<deviceId>-YYYY-MM-DD.log`), so it reflects exactly what the background sync retrieved without requiring database reads.

### 5. `GET /api/reference/device-apis`
- **Purpose:** Thin wrapper over the highlights from `docs/official_api_reference.md`. Returns a JSON list describing the most commonly used TLINK device endpoints so developers can jump between this local store and the live SaaS API.

## Database Schema Overview

| Table | Description |
| --- | --- |
| `users` | Represents TLINK `deviceUserid` / `userId` owners. Internal primary key is a UUID (`CHAR(36)`) generated automatically. |
| `devices` | `deviceId` entities bound to a `user_id` (UUID FK). Stores the last push metadata plus descriptive fields such as `device_name`, `device_no`, `group_id`, lat/lng, `product_id`, `product_type`, and `protocol_label`. |
| `sensors` | Unique per `(device, sensorsId)` pairing. Tracks last-known status along with the vendor-reported `unit`. |
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
