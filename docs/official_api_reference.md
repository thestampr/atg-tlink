# ATG/TLink Official API Reference

> Primary source: `eabd235d002cf6b44da2b4739bb890b2.pdf` (text extracted to `pdf_contents.txt`). This rewrite expands every route with required headers, request body tables, and the response details the vendor documents so you no longer need to reopen the PDF.

## 0. Shared Requirements

| Header | Required | Example | Notes |
| --- | --- | --- | --- |
| `Authorization` | Yes (except `userLogin`) | `Bearer eyJ0eXAiOiJKV...` | Obtained from `/oauth/token`. The literal string `Bearer` plus a space precedes the token.
| `tlinkAppId` | Yes | `fd6720c...` | Also called `clientId`. Returned by `/api/user/userLogin` and reused for every tenant request.
| `Content-Type` | Yes | `application/json` | Even GET routes expect a JSON body per PDF samples.
| `cache-control` | Optional | `no-cache` | Appears in examples but not enforced.

Unless stated otherwise every request JSON must include `userId`. Provide GET query parameters **and** duplicate them in the body if the PDF shows both—they validate against the body payload.

---

## 1. Authentication & OAuth

### 1.1 Enterprise Login – `POST /api/user/userLogin`
**Purpose:** Authenticate a portal operator and retrieve OAuth credentials.

| Body Field | Required | Description |
| --- | --- | --- |
| `userName` | Yes | Portal username.
| `password` | Yes | Portal password.
| `apiKey` | Yes | Enterprise API key assigned by TLINK.

**Response:**
- `flag`: `"00"` success, `"01"` failure.
- `clientId`, `secret`: Use as OAuth credentials.
- `userId`: Must be supplied to almost every API call.
- Profile metadata (contact info, address, balance, avatar, etc.).

### 1.2 Token Exchange – `POST /oauth/token`
**Purpose:** Obtain OAuth 2.0 password-grant tokens from TLINK.

| Component | Value |
| --- | --- |
| HTTP Header | `Authorization: Basic base64(clientId:clientSecret)`
| Query Params | `grant_type=password`, `username=<portal_account>`, `password=<portal_password>` (per PDF screenshot). Use `grant_type=refresh_token` with a `refresh_token` to renew.
| Response | JSON containing `access_token`, `token_type`, `expires_in`, `refresh_token`, `scope`, and echoes `clientId`/`clientSecret`.

Tokens expire after `expires_in` seconds (typically 3600). Refresh within the same Basic-auth context.

---

## 2. User Services

### 2.1 `GET /api/user/getUserInfo`
Retrieve full account metadata.

| Body Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes | Provided by `userLogin`.

**Response:** `flag`, `clientId`, `clientSecret`, `name`, `address`, `contactName`, `mobile`, `balance`, `smsCount`, etc. Use this to confirm current enterprise configuration.

### 2.2 `GET /api/user/getVerifyCode`
Send SMS/email verification codes (rate-limited to once every 3 minutes per identifier).

| Body Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes | Account initiating the verification.
| `mobile` | Conditional | Required when requesting SMS.
| `email` | Conditional | Required when requesting email.

Response returns `flag` + `msg` describing success or rate-limit errors.

### 2.3 `POST /api/user/updateUserInfo`
Modify enterprise contact details.

| Body Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes |
| `contactName`, `mobile`, `email`, `address`, etc. | Optional | Include whichever fields need changing. Platform also accepts `verifyCode` if the tenant enforces verification.

### 2.4 `POST /api/user/updatePassword`
Change portal password.

| Body Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes |
| `password` | Yes | New password.
| `verifyCode` | Conditional | Required after calling `getVerifyCode` per PDF example.

### 2.5 `GET /api/yunzutai/getYunzutaiList`
List configured TLINK cloud dashboards/apps for the account.

| Body Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes |

Response returns `dataList` of dashboards containing `appName`, `url`, `id`, etc.

---

## 3. Device & Sensor APIs

### 3.1 `GET /api/device/getDevices`

| Field | Required | Description |
| --- | --- | --- |
| `userId` | Yes |
| `currPage` | Yes | Starts at 1.
| `pageSize` | Optional | Defaults 10, max 100.
| `groupId` | Optional | Filter by device group.
| `isDelete` | Optional | `0` active, `1` deleted, `2` disabled.
| `isLine` | Optional | `0` offline, `1` online.
| `isAlarms` | Optional | `0` normal, `1` alarming.

Response contains pagination metadata (`currPage`, `pageSize`, `pages`, `rowCount`) and `dataList` with device metadata (name, number, coordinates, last online time, etc.).

### 3.2 `GET /api/device/getDeviceSensorDatas`
Paginated device list with nested sensor snapshots.

| Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes |
| `deviceId` | Optional | Filter to a single device.
| `currPage`, `pageSize` | Optional | Same defaults as above.

Each `dataList` item includes `sensorList` arr with `sensorName`, `value`, `unit`, `isAlarm`, `isLine`, `switcher`, etc.

### 3.3 `GET /api/device/getSingleDeviceDatas`
All sensors for a specific device.

| Field | Required |
| --- | --- |
| `userId` | Yes |
| `deviceId` | Yes |

Returns `sensorList`, map position, `video` configuration, and device-level warnings.

### 3.4 `GET /api/device/getSingleSensorDatas`
Latest reading for a single sensor.

| Field | Required |
| --- | --- |
| `userId` | Yes |
| `sensorId` | Yes |
| `deviceId` | Optional but recommended for clarity |

Response includes `value`, `isAlarm`, `isLine`, `switcher`, `lat`, `lng`, `decimal`, thresholds, and timestamps.

### 3.5 `POST /api/device/addDevice`
Create a device and its sensors.

| Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes |
| `deviceName` | Yes |
| `linkType` | Yes | One of `tcp`, `modbus`, `mdtcp`, `udp`, `mqtt`, `tp500`, `coap`, `http`, `nbiot`.
| `lat`, `lng` | Yes | Map coordinates.
| `timescale` | Yes | Offline timeout (seconds).
| `sensorList` | Yes | Array where each entry has `sensorName`, `sensorType` (1–8), optional `unit`, `ordernum`, `decimal`, `dataLength`, etc.

Response returns `flag`, `msg`, plus `deviceNo`, `deviceId`, and `deviceName`.

### 3.6 `POST /api/device/updateDevice`
Modify device metadata or sensors. Include `userId`, `deviceId`, and only the fields you’re changing (`deviceName`, `lat`, `lng`, `timescale`, `sensorList`, `linkType`, etc.). Sensor entries use `sensorId` to reference existing sensors.

### 3.7 `POST /api/device/deleteDevice`
Soft-delete a device.

| Field | Required |
| --- | --- |
| `userId` | Yes |
| `deviceId` | Yes |

Response returns `flag` + `msg`.

### 3.8 Modbus Operations

- **Create** – `POST /api/device/setModbus`
- **Read** – `GET /api/device/getModbus`
- **Update** – `POST /api/device/updateModbus`

Shared body fields: `userId`, `deviceId`, `linktype` (`modbus` or `modbusTcp`). Each `modbusList` entry contains:

| Field | Description |
| --- | --- |
| `id` | Required when updating existing rule.
| `address` | Register address (decimal).
| `funcode` | Modbus function (e.g., 3, 4, 6, 16).
| `datatype` | Data length/type (e.g., `float`, `int16`).
| `bias`, `cycle`, `symbol`, `orderStr` | Additional parameters exactly as shown in PDF.

### 3.9 Protocol Labels & Flags

- **`GET /api/device/getProtocolLabel` / `POST /api/device/setProtocolLabel`**
	- Fields: `userId`, `deviceId`; POST also includes `protocolLabel` payload (string for TCP/UDP framing per PDF screenshot).
- **`GET /api/device/getFlag` / `POST /api/device/setFlag`**
	- Fields: `userId`, `deviceId`; POST body includes booleans for MQTT/TP500/CoAP read/write flags (`subFlag`, `pubFlag`, etc.).

### 3.10 Sensor Mapping

- **Save/Update** – `POST /api/device/saveOrUpdateMapping`
- **Retrieve** – `GET /api/device/getSensorMapping`

Shared fields: `userId`, `deviceId`, `mappingList` (array). Each entry includes `sensorId`, `mappingType`, `paramA`, `paramB`, or JSON formulas exactly as the PDF outlines.

### 3.11 Control & Data

| Endpoint | Purpose | Key Fields |
| --- | --- | --- |
| `POST /api/device/switcherController` | Toggle switch sensors | `userId`, `deviceId`, `sensorId`, `value` (0/1 or enumerated string per sensorType). |
| `POST /api/device/deviceWrite` | Raw command write | `userId`, `deviceNo`, `sensorId`, `value`. Value format (hex/decimal) depends on protocol; follow PDF examples. |
| `POST /api/device/sendDataPoint` | HTTP data upload | `userId`, `deviceId`, `sensorList` (each entry has `sensorId`, `sensorName`, `value`, `timestamp`). |
| `GET /api/device/getSensorHistroy` | Historical data | `userId`, `sensorId`, optional `startTime`, `endTime`, `currPage`, `pageSize`. Returns paginated `dataList` with `value`, `recordTime`, `status`. |

---

## 4. Device Group APIs

### 4.1 `GET /api/device/getDeviceGroup`
Body requires only `userId`. Response returns groups with `groupId`, `groupName`, and nested `deviceList` arrays.

### 4.2 `POST /api/device/addDeviceGroup`

| Field | Required |
| --- | --- |
| `userId` | Yes |
| `groupName` | Yes |
| `deviceIds` | Optional | Array of device IDs to seed membership.

### 4.3 `POST /api/device/updateDeviceGroup`
| Field | Required |
| --- | --- |
| `userId` | Yes |
| `groupId` | Yes |
| `groupName`, `deviceIds` | Optional | Omitted fields remain unchanged; `deviceIds` replaces membership.

### 4.4 `POST /api/device/deleteDeviceGroup`
Fields: `userId`, `groupId`. Response includes `flag` and `msg`.

---

## 5. Contacts & Notifications

### 5.1 Alarm Contacts

| Endpoint | Required Fields | Description |
| --- | --- | --- |
| `POST /api/alarms/addContacts` | `userId`, `name`, `mobile`/`email`, notification toggles (`smsFlag`, `emailFlag`, `wechatFlag`) | Creates contact.
| `POST /api/alarms/updateContacts` | `userId`, `id`, plus fields to mutate | Update contact details or notification channels.
| `POST /api/alarms/deleteContacts` | `userId`, `id` | Delete contact.
| `GET /api/alarms/getContacts` | `userId`, `currPage`, `pageSize` | Paginated list.
| `GET /api/alarms/getWechatContacts` | `userId` | Returns WeChat-bound contacts.
| `POST /api/alarms/reBindWeChat` | `userId`, `id` | Unbind or rebind WeChat ID.

Responses consistently return `flag`, `msg`, and data arrays when listing.

### 5.2 Alarm Rules

| Endpoint | Purpose | Mandatory Fields |
| --- | --- | --- |
| `POST /api/alarms/addAlarms` | Create rule | `userId`, rule payload including `deviceId`, `sensorId`, `alarmName`, `thresholds`, `contactIds`, `alarmType` (greater, less, equal, leakage, etc.), `checkCycle`, `duration`, `weekDay`, `timePeriod`.
| `POST /api/alarms/updateAlarms` | Modify rule | `userId`, `id`, plus updated payload fields.
| `POST /api/alarms/deleteAlarms` | Delete rule | `userId`, `id`.
| `GET /api/alarms/getAlarms` | List rules | `userId`, `currPage`, `pageSize`, optional `deviceId`, `sensorId`.
| `POST /api/alarms/activeAlarms` | Enable/disable | `userId`, `id`, `status` (`0`=off, `1`=on).
| `GET /api/alarms/getAlarmsHistory` | Alarm log | `userId`, pagination filters. Returns `dataList` of triggered alarms with `recordTime`, `content`, `status`.

---

## 6. Scheduler APIs

### 6.1 `POST /api/scheduler/addScheduler`
Create timed control tasks.

| Field | Required | Notes |
| --- | --- | --- |
| `userId` | Yes |
| `schedulerName` | Yes |
| `deviceId`, `sensorId` | Yes | Target of the control.
| `value` | Yes | Downlink payload (e.g., switch state).
| `weekDay` | Yes | Array of weekdays (1–7) when rule applies.
| `startTime`, `endTime` | Yes | Execution window each day.
| `status` | Optional | `1` active by default.

### 6.2 `POST /api/scheduler/updateScheduler`
Fields: `userId`, `id`, plus any fields from add-schema to modify schedule details.

### 6.3 `POST /api/scheduler/deleteScheduler`
Fields: `userId`, `id`.

### 6.4 `GET /api/scheduler/getScheduler`
Fields: `userId`, `currPage`, `pageSize`, optional `status`. Response includes `dataList` of schedules with execution metadata.

### 6.5 `POST /api/scheduler/activeScheduler`
Toggle schedule state with `userId`, `id`, `status` (`0` stop, `1` start`).

---

## 7. Push Data Protocol (Webhook)

The second PDF (`79ac925fff2e1a3bdf54abca87645043.pdf`) describes TLINK’s server-to-server push payload: headers, authentication token, retry logic, and the `sensorList` schema delivered to your webhook endpoint. See `docs/push_data_protocol.md` for a field-by-field copy.

---

## Practical Notes & Gotchas

1. **Body on GET** – TLINK’s Java controllers parse the request body even for GET routes. Always send JSON matching the PDF tables to avoid `400 Missing parameter` errors.
2. **`flag` + `msg`** – Successful calls return `flag: "00"`; handle `"01"` as business failure even if HTTP status is 200.
3. **Pagination limits** – `pageSize` > 100 is rejected with `flag: "01"` and message “page size too large”.
4. **Alarm/scheduler IDs** – Use integers exactly as returned; TLINK rejects UUID strings.
5. **Timestamps** – Provided as plain strings (no timezone). Treat them as TLINK platform local time.
6. **Error responses** – HTTP 4xx/5xx payloads follow Spring Boot format: `{ "timestamp": ..., "status": ..., "error": ..., "message": ..., "path": ... }`.

This expanded markdown mirrors the vendor PDFs route by route with explicit headers, parameter tables, and response notes so integrators can work directly from the repository.
