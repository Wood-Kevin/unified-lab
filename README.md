# Unified Lab

A containerized observability stack that collects Linux system telemetry, stores it in PostgreSQL, and exposes it through Prometheus, Grafana, and a lightweight web dashboard.

---

## Architecture

```
                        ┌─────────────────────────────────────────┐
                        │              backend-net                 │
                        │                                          │
  ┌──────────────┐      │  ┌─────────────┐    ┌────────────────┐  │
  │  Host /proc  │──────┼─▶│ telemetry-  │───▶│  metrics-db    │  │
  │  (bind mount)│      │  │    app      │    │  (PostgreSQL)  │  │
  └──────────────┘      │  │  :5000      │    │  (internal)    │  │
                        │  └──────┬──────┘    └────────────────┘  │
                        │         │ /metrics                       │
                        │         ▼                                │
                        │  ┌─────────────┐    ┌────────────────┐  │
                        │  │ prometheus  │───▶│ alertmanager   │  │
                        │  │   :9090     │    │    :9093       │  │
                        │  └─────────────┘    └────────────────┘  │
                        │         │                                │
                        │         ▼                                │
                        │  ┌─────────────┐                        │
                        │  │   grafana   │                        │
                        │  │   :3001     │                        │
                        │  └─────────────┘                        │
                        └──────────┬──────────────────────────────┘
                                   │
                        ┌──────────┴──────────────────────────────┐
                        │              frontend-net                │
                        │                                          │
                        │  ┌─────────────┐    ┌────────────────┐  │
                        │  │ web-        │◀───│ telemetry-app  │  │
                        │  │ dashboard   │    │  (shared)      │  │
                        │  │   :8080     │    └────────────────┘  │
                        └──────────────────────────────────────────┘
```

---

## Services

| Service | Container | Port | Purpose |
|---|---|---|---|
| `telemetry-app` | `app-tier` | 5000 | Flask API + background collector thread + Prometheus `/metrics` endpoint |
| `metrics-db` | `database-tier` | internal | PostgreSQL 15 — persists telemetry rows |
| `prometheus` | `metrics-storage` | 9090 | Scrapes `telemetry-app:5000/metrics` every 5s; evaluates alert rules |
| `alertmanager` | `alertmanager` | 9093 | Receives alerts from Prometheus; routes and deduplicates |
| `grafana` | `metrics-visualizer` | 3001 | Dashboards backed by Prometheus; auto-provisioned |
| `web-dashboard` | `web-tier` | 8080 | Lightweight HTML dashboard that proxies `/api/load` from `telemetry-app` |

Networks: `backend-net` (telemetry-app, metrics-db, prometheus, alertmanager, grafana) and `frontend-net` (telemetry-app, web-dashboard, grafana). The database has no host-side port.

---

## Quick Start

```bash
# Start the full stack
docker compose up -d

# Tail logs for a specific service
docker compose logs -f telemetry-app

# Restart a single service after editing its source file
docker compose restart telemetry-app

# Rebuild and restart a service after editing the Dockerfile
docker compose up -d --build telemetry-app

# Stop everything (preserves volumes)
docker compose down

# Stop and wipe all volumes (destroys stored metrics)
docker compose down -v
```

### Service URLs

| URL | Service |
|---|---|
| http://localhost:5000 | Telemetry API health check |
| http://localhost:5000/api/load | Latest telemetry row as JSON |
| http://localhost:5000/metrics | Prometheus exposition format |
| http://localhost:8080 | Web dashboard |
| http://localhost:9090 | Prometheus UI |
| http://localhost:9090/alerts | Active alert rules |
| http://localhost:9093 | Alertmanager UI |
| http://localhost:3001 | Grafana (admin / see Grafana docs for password) |

---

## Database

```bash
# Interactive psql session
docker compose exec metrics-db psql -U postgres -d telemetry

# Manual backup
bash backup_db.sh
```

- **Host**: `metrics-db` (Docker internal hostname)
- **DB**: `telemetry` · **User**: `postgres` · **Password**: `postgres_password`
- **Table**: `system_telemetry(id, timestamp, load_1min, load_5min, load_15min)`

---

## Prometheus Alert Rules

Defined in `prometheus/rules/unified-lab.yml`, loaded into the Prometheus container at `/etc/prometheus/rules/`.

| Alert | Expression | For | Severity | Meaning |
|---|---|---|---|---|
| `CollectorSilent` | `time() - collector_last_write_unix > 10` | 30s | critical | Collector thread has stopped inserting rows |
| `DatabaseDown` | `db_connected == 0` | 15s | critical | telemetry-app cannot connect to PostgreSQL |
| `HighErrorRate` | `rate(flask_requests_total{http_status_code=~"5.."}[1m]) > 0.01` | 1m | warning | More than 0.01 5xx responses per second |
| `HighRequestLatency` | `histogram_quantile(0.95, ...) > 0.5` | 2m | warning | p95 request latency above 500ms |
| `TableGrowthStalled` | `rate(collector_rows_total[5m]) == 0` | 1m | warning | No new rows inserted in the last 5 minutes |

Alerts are sent to Alertmanager at `alertmanager:9093`. The current Alertmanager config (`alertmanager.yml`) uses a null receiver — alerts are visible in the UI but not forwarded externally.

---

## Grafana Dashboard

The Unified Lab dashboard is auto-provisioned on container start — no manual import required.

| File | Purpose |
|---|---|
| `grafana/dashboards/unified-lab.json` | Dashboard definition |
| `grafana/provisioning/dashboards/default.yaml` | Tells Grafana to load dashboards from `/etc/grafana/dashboards` |
| `grafana/provisioning/datasources/prometheus.yaml` | Configures Prometheus at `http://prometheus:9090` as the default datasource |

Both provisioning directories are bind-mounted into the Grafana container via `compose.yaml`. Changes to the JSON file take effect after `docker compose restart grafana`.

Dashboard panels: DB Connected · Collector Lag · DB Row Count · Flask Request Rate · Flask p95 Latency · Collector Insert Rate · System Memory Usage · System Load 1m

---

## Runbooks

| Alert | Runbook |
|---|---|
| `DatabaseDown` | [runbooks/database-down.md](runbooks/database-down.md) |
| `CollectorSilent` | [runbooks/collector-silent.md](runbooks/collector-silent.md) |
