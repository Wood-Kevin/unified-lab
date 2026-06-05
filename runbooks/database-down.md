# Runbook: DatabaseDown

## Alert Summary

| Field | Value |
|---|---|
| **Alert name** | `DatabaseDown` |
| **Severity** | critical |
| **Prometheus rule** | `db_connected == 0` for 15 seconds |
| **What it means** | The `telemetry-app` container cannot establish a connection to PostgreSQL. The API will return 500s on `/api/load`, and the collector thread will stop persisting metrics. |

---

## Symptoms

**Prometheus / Alertmanager**
- `DatabaseDown` alert firing at `http://localhost:9090/alerts`
- `db_connected` gauge reads `0`
- `collector_last_write_unix` stops advancing (triggers `CollectorSilent` within 30s)
- `db_row_count` stops growing

**Grafana** (`http://localhost:3001`)
- "DB Connected" stat panel shows **DOWN** (red background)
- "Collector Lag" stat panel climbs above 10s and turns red
- "DB Row Count" time series flatlines

**Telemetry app logs**
```
Error in metrics collector daemon: could not connect to server: Connection refused
```

**Web dashboard** (`http://localhost:8080`)
- Returns a 500 or shows stale data

---

## Possible Causes

1. `metrics-db` container has stopped or crashed
2. PostgreSQL is still starting up and not yet accepting connections
3. The `pgdata` volume is corrupted or full
4. A `docker compose down -v` was run, wiping the database volume
5. Host ran out of memory and the OOM killer terminated the PostgreSQL process

---

## Diagnosis Steps

**1. Check container status**
```bash
docker compose ps
```
Look for `database-tier` — it should show `Up`. If it shows `Exit` or is absent, the container is down.

**2. Check PostgreSQL logs**
```bash
docker compose logs --tail=50 metrics-db
```
Look for crash messages, OOM kills, or disk-full errors.

**3. Confirm the metric value in Prometheus**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=db_connected' | python3 -m json.tool
```
A healthy stack returns `"value": [<timestamp>, "1"]`. A value of `"0"` or no result confirms the alert.

**4. Check telemetry-app logs for connection errors**
```bash
docker compose logs --tail=50 telemetry-app
```

**5. Check host disk space**
```bash
df -h /var/lib/docker
```
A full disk will prevent PostgreSQL from writing WAL and will cause it to crash.

---

## Remediation Steps

**If the container is stopped — restart it**
```bash
docker compose start metrics-db
```
Wait 5–10 seconds for PostgreSQL to finish initializing, then verify with `docker compose ps`.

**If the container crashed with an error — full restart**
```bash
docker compose down metrics-db
docker compose up -d metrics-db
```

**If the pgdata volume is corrupted**
```bash
# WARNING: destroys all stored metrics
docker compose down
docker volume rm unified-lab_pgdata
docker compose up -d
```

**If the host is out of disk space**
Clean up unused Docker resources:
```bash
docker system prune -f
```
Then restart the database:
```bash
docker compose start metrics-db
```

---

## Verification Steps

**1. Confirm the container is running**
```bash
docker compose ps metrics-db
```

**2. Confirm PostgreSQL is accepting connections**
```bash
docker compose exec metrics-db psql -U postgres -d telemetry -c "SELECT 1;"
```
Expected output: `?column? ---------- 1`

**3. Confirm `db_connected` has returned to 1**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=db_connected' | python3 -m json.tool
```

**4. Confirm the collector is writing again**
```bash
curl -s 'http://localhost:9090/api/v1/query?query=time()-collector_last_write_unix' | python3 -m json.tool
```
Value should be under 5 seconds.

**5. Confirm the alert has resolved in Prometheus**
- Visit `http://localhost:9090/alerts` — `DatabaseDown` should show as `inactive`

---

## Escalation Criteria

Escalate to L2 if any of the following are true:

- The `pgdata` volume shows signs of corruption (PostgreSQL logs `invalid page` or `WAL file is missing`)
- Disk is full and cannot be cleared without risk to other services
- The container restarts repeatedly (restart loop visible in `docker compose ps`)
- `db_connected` remains `0` more than 5 minutes after the database container is confirmed running
- Data loss is suspected (row count significantly lower than expected)

---

## Related Alerts

| Alert | Relationship |
|---|---|
| `CollectorSilent` | Fires within 30s of `DatabaseDown` — the collector thread cannot write rows when the DB is unreachable |
| `TableGrowthStalled` | Fires within 1m — `collector_rows_total` stops incrementing when inserts fail |

Both related alerts will auto-resolve when `DatabaseDown` resolves.
