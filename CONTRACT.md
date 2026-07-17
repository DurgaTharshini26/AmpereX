# AmpereX — Data Contract (READ FIRST, ALWAYS)

This file is the single source of truth for how data is shaped and named across
the whole system. Everyone's code — no matter which AI tool generated it —
must match this exactly. If something needs to change, edit this file first,
push it, and tell the team in the group chat before changing code.

---

## 1. MQTT Topics

```
campus/solar/data
campus/wind/data
campus/battery/data
campus/load/data
```

A subscriber can catch all four at once with the wildcard: `campus/+/data`

Owned by: Member 3 (publishes) and Member 5 (subscribes)

---

## 2. MQTT Message Format (JSON)

Every message published to any of the 4 topics above MUST look like this:

```json
{
  "value": 452.3,
  "unit": "watts",
  "device_id": "solar-sim-1",
  "timestamp": "2026-07-17T10:15:30.000Z"
}
```

| Field       | Type   | Notes                                                        |
|-------------|--------|----------------------------------------------------------------|
| value       | float  | the reading itself                                             |
| unit        | string | "watts" for solar/wind/load, "percent" for battery             |
| device_id   | string | e.g. "solar-sim-1" — lets you support multiple devices later   |
| timestamp   | string | ISO 8601, UTC, e.g. `datetime.now(timezone.utc).isoformat()`   |

---

## 3. InfluxDB Schema

| Concept      | Value            |
|--------------|-------------------|
| Bucket       | `sensor_data`     |
| Measurement  | `sensor_reading`  |
| Tags         | `sensor_type` (solar/wind/battery/load), `device_id`, `unit` |
| Field        | `value` (float)   |
| Time         | taken from the message's `timestamp` |

Owned by: Member 5

---

## 4. FastAPI REST Endpoints (what Member 2 exposes to frontend)

```
GET /dashboard        -> latest reading for all 4 sensor types
GET /forecast          -> Prophet predictions (Member 4's output)
GET /recommendations   -> optimization engine output (Member 4's output)
```

Owned by: Member 2 — but Member 2's `/dashboard` endpoint will query InfluxDB
using the schema in section 3, so if that schema changes, Member 2's queries
break. Tell them before changing it.

---

## 5. Environment Variables (every module reads config this way, never hardcoded)

```
MQTT_HOST=localhost
MQTT_PORT=1883

INFLUX_URL=http://localhost:8086
INFLUX_TOKEN=<your token>
INFLUX_ORG=ampereX
INFLUX_BUCKET=sensor_data
```

Each person's module folder has its own `.env` (never committed — only
`.env.example` is committed) so everyone can run the same code with their own
local broker/database.

---

## 6. Git workflow (why this avoids branch conflicts)

- Each member works in their own top-level folder (`/simulator`, `/subscriber`,
  `/backend`, `/frontend`, `/ml`) — different folders means Git rarely sees
  overlapping changes, so merges are close to automatic.
- This `CONTRACT.md` is the only file everyone touches — treat changes to it
  as requiring a heads-up to the team, since it's the thing that keeps
  everyone's independently-AI-generated code compatible.
