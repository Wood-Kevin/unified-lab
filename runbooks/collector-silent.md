# Runbook: CollectorSilent

## Alert Summary

| Field | Value |
|---|---|
| **Alert name** | `CollectorSilent` |
| **Severity** | critical |
| **Prometheus rule** | `time() - collector_last_write_unix > 10` for 30 seconds |
| **What it means** | The background collector thread inside `telemetry-app` has not successfully inserted a row into PostgreSQL in over 10 seconds. Under normal operation the thread writes every 2 seconds. A lag above 10 seconds indicates the thread has stalled, panicked, or the container is down. |

---

## Symptoms

**Prometheus / Alertmanager**
- `CollectorSilent` alert firing at `http://localhost:9090/alerts`
- `time() - collector_last_write_unix` exceeds 10 and climbs continuously
- `collector_rows_total` rate drops to 0 (also triggers `TableGrowthStalled`)
- `db_row_count` flatlines

**Grafana** (`http://localhost:3001`)
- "Collector Lag" stat panel turns yellow (>10s) then red (>30s)
- "Collector Insert Rate" time series drops to 0
- "DB Row Count" time series flatlines

**Telemetry app logs**
```
# Container down:
(no output — container not running)

# Thread crashed with DB error:
Error in metrics collector daemon: could not connect to server: Connection refused

# Thread crashed with unexpected error:
Error in metrics collector daemon: <traceback>
```

**Web dashboard** (`http://localhost:8080`)
- Still serves requests (Flask API is independent of the collector thread) but data is stale

---

## Possible Causes

1. The `telemetry-app` container has stopped or crashed
2. The collector background thread raised an unhandled exception and exited its loop
3. PostgreSQL became unreachable, causing all insert attempts to fail (see `DatabaseDown`)
4. The container is running but severely resource-starved (CPU throttling, OOM)
5. The host `/proc` filesystem is unavailable, causing `os.getloadavg()` to fail

---

## Diagnosis Steps

**1. Check container status**
```bash
docker compose ps telemetry-app
```
If `app-tier` shows `Exit` or is absent, the container is down — skip to Remediation.

**2. Check how long since the last write**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=time()-collector_last_write_unix' | python3 -m json.tool
```
A value of several minutes means the thread has been silent a long time. No result at all means `telemetry-app` is not being scraped (container down or `/metrics` unreachable).

**3. Check telemetry-app logs for errors**
```bash
docker compose logs --tail=100 telemetry-app
```
Look for:
- `Error in metrics collector daemon` — thread is running but failing on each iteration
- No output at all after the startup lines — thread may have exited silently

**4. Check if the Flask API is still responding**
```bash
curl -s http://localhost:5000/
```
If this returns `{"status": "healthy"}`, the Flask process is alive but the collector thread has died. If it times out, the container is down entirely.

**5. Check if the database is the root cause**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=db_connected' | python3 -m json.tool
```
If `db_connected` is `0`, resolve `DatabaseDown` first — `CollectorSilent` will follow.

**6. Check container resource usage**
```bash
docker stats app-tier --no-stream
```

---

## Remediation Steps

**If the container is stopped — restart it**
```bash
docker compose start telemetry-app
```

**If the container is running but the thread has died — restart the container**

The collector thread is a daemon thread with no watchdog. If it exits its loop, the only recovery is a container restart:
```bash
docker compose restart telemetry-app
```

**If repeated crashes are occurring — rebuild the container**
```bash
docker compose up -d --build telemetry-app
```

**If the database is unreachable (root cause)**
Follow the `DatabaseDown` runbook first. The collector thread will automatically reconnect and resume writing once PostgreSQL is available — no additional action needed.

---

## Verification Steps

**1. Confirm the container is running**
```bash
docker compose ps telemetry-app
```

**2. Confirm the collector is writing**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=time()-collector_last_write_unix' | python3 -m json.tool
```
Value should be under 5 seconds within 10–15 seconds of the container starting.

**3. Confirm the insert rate has recovered**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=rate(collector_rows_total[1m])' | python3 -m json.tool
```
Expect approximately `0.5` (one insert per 2 seconds).

**4. Confirm new rows are appearing in the database**
```bash
docker compose exec metrics-db psql -U postgres -d telemetry \
  -c "SELECT id, timestamp FROM system_telemetry ORDER BY id DESC LIMIT 3;"
```
Timestamps should be within the last few seconds.

**5. Confirm the alert has resolved**
- Visit `http://localhost:9090/alerts` — `CollectorSilent` should show as `inactive`

---

## Escalation Criteria

Escalate to L2 if any of the following are true:

- The container restarts in a loop (visible in `docker compose ps` as repeated restarts)
- The Flask API health check (`GET /`) is returning 500s, indicating the main process is unhealthy
- `collector_last_write_unix` remains stale more than 5 minutes after the container is confirmed running and the database is confirmed healthy
- Logs show a Python traceback in the collector loop that is not a transient DB connection error

---

## Related Alerts

| Alert | Relationship |
|---|---|
| `DatabaseDown` | Most common root cause of `CollectorSilent` — resolve it first |
| `TableGrowthStalled` | Always co-fires with `CollectorSilent`; resolves automatically when the collector resumes |
