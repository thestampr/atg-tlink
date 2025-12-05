# Platform Data Push Transmission Protocol

This document summarizes the integration details from `79ac925fff2e1a3bdf54abca87645043.pdf`, which describes how the ATG/TLink IoT platform pushes device readings to an application server after you subscribe to "Device Data Update Notification" events.

## Workflow Overview

1. **Subscribe** to the "Device Data Update Notification" callback inside the vendor console. The PDF uses `http://www.moniiot.com/api/getPushData.htm` as an example endpoint; replace it with your public HTTPS URL (for example, `https://your-domain.com/api/webhooks/tlink`).
2. **Platform Push** occurs whenever a device uploads sensor values. The IoT platform issues an HTTP(S) POST to the subscribed URL and places the payload in the request body as JSON.
3. **Your Server** should validate the request (optional shared secret), parse the JSON payload, persist the device/sensor information, and respond with HTTP 200 to acknowledge receipt. No other response payload is required according to the document.

## HTTP Contract

| Item | Value |
| --- | --- |
| Method | `POST` |
| Content-Type | `application/json` |
| Body | JSON object containing device, sensor, and transmission metadata |
| Response | `200 OK` indicates success; no response body required |

## Payload Structure

```json
{
  "flag": "00",
  "deviceUserid": 385,
  "parentUserId": "217",
  "sensorsDates": [
    {
      "times": "14:16:21",
      "sensorsId": 11922,
      "isAlarm": "0",
      "sensorsTypeId": 1,
      "isLine": 1,
      "reVal": "5.0000",
      "value": "5.0"
    }
  ],
  "time": "2019-05-10 14:16:21",
  "rawData": "23525455...",
  "deviceId": 2864
}
```

### Field Reference

| Field | Type | Description |
| --- | --- | --- |
| `flag` | `string` | Result indicator (`"00"` = success). |
| `deviceUserid` | `number/string` | User identifier tied to the device. |
| `parentUserId` | `string` | Enterprise/tenant ID (sometimes called cloud/organization). |
| `sensorsDates` | `array<object>` | Collection of sensor readings. Each entry includes the timestamp, sensor metadata, and raw/mapped values. |
| `sensorsDates[].times` | `string` | Local time when the sample was produced (`HH:MM:SS`). |
| `sensorsDates[].sensorsId` | `number` | Sensor identifier defined in the vendor portal. |
| `sensorsDates[].sensorsTypeId` | `number` | Sensor type (1 = numeric, 2 = writable switch, etc.). |
| `sensorsDates[].isAlarm` | `string` | Alarm flag (`"0"` = normal, `"1"` = alarm). |
| `sensorsDates[].isLine` | `number` | Connectivity flag (`1` online, `0` offline). |
| `sensorsDates[].reVal` | `string` | Raw value returned by the device. |
| `sensorsDates[].value` | `string` | Mapped value after the platform applies scaling or unit conversions. |
| `time` | `string` | "Sending time" in `YYYY-MM-DD HH:MM:SS` format. Often matches the latest `times` inside `sensorsDates`. |
| `rawData` | `string` | Hexadecimal payload for the full sensor frame (optional but useful for auditing). |
| `deviceId` | `number` | Device identifier (matches values used in the REST APIs). |

## Example Exchange

**Request**
```
POST /api/webhooks/tlink HTTP/1.1
Host: your-domain.com
Content-Type: application/json
```

Body:
```json
{
  "flag": "00",
  "deviceUserid": 385,
  "parentUserId": "217",
  "sensorsDates": [
    {"times": "14:16:21", "sensorsId": 11922, "isAlarm": "0", "sensorsTypeId": 1, "isLine": 1, "reVal": "5.0000", "value": "5.0"},
    {"times": "14:16:21", "sensorsId": 11923, "isAlarm": "0", "sensorsTypeId": 1, "isLine": 1, "reVal": "2.7434", "value": "28.6"},
    {"times": "14:16:21", "sensorsId": 11924, "isAlarm": "0", "sensorsTypeId": 1, "isLine": 1, "reVal": "0.0077", "value": "0"}
  ],
  "time": "2019-05-10 14:16:21",
  "rawData": "235254552C352E303030302C322E373433342C302E303037370D0A",
  "deviceId": 2864
}
```

**Response**
```
HTTP/1.1 200 OK
```

No body is required; the vendor only checks the HTTP status.

## Implementation Notes

- **Security**: The PDF does not define authentication for the webhook. In practice, you should enforce HTTPS and add your own verification (e.g., shared secret header or HMAC) because the platform will call whatever URL you register.
- **Idempotency**: The platform may retry deliveries if it doesn’t receive `200 OK`. Make your handler idempotent by deduplicating on `(deviceId, sensorsId, time)` or storing last processed timestamps.
- **Time Zones**: Timestamps are strings without timezone information. Treat them as local device/platform time or attach your own timezone during ingestion.
- **Schema Drift**: Unknown fields can safely be ignored. Log the full payload (including `rawData`) if you need forensic visibility.

This markdown file captures the key expectations so you can implement or audit your webhook handler without referring back to the original PDF.
