# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack & Services

This is a containerized observability stack managed entirely via Docker Compose. There is no build system, package manager, or test framework — all runtime behavior lives inside containers.

Five services defined in `compose.yaml`:

| Service | Container | Port | Purpose |
|---|---|---|---|
| `metrics-db` | `database-tier` | (internal only) | PostgreSQL 15 — persists telemetry rows |
| `telemetry-app` | `app-tier` | 5000 | Flask API + background collector thread + Prometheus `/metrics` endpoint |
| `web-dashboard` | `web-tier` | 8080 | Minimal Python HTTP server that proxies JSON from `telemetry-app` |
| `prometheus` | `metrics-storage` | 9090 | Scrapes `telemetry-app:5000/metrics` every 5s |
| `grafana` | `metrics-visualizer` | 3001 | Dashboards backed by Prometheus |

Networks: `backend-net` (db + app + prometheus + grafana) and `frontend-net` (app + dashboard + grafana). The database has **no host-side port** — it is only reachable from within `backend-net`.

## Common Commands

```bash
# Start the full stack (detached)
docker compose up -d

# Tail logs for a specific service
docker compose logs -f telemetry-app

# Restart a single service after editing its source file
docker compose restart telemetry-app

# Stop everything
docker compose down

# Stop and wipe all volumes (destroys stored metrics)
docker compose down -v

# Manual database backup (runs pg_dump inside the running container)
bash backup_db.sh
```

## Architecture

`app.py` runs two concurrent roles inside one container:
1. **Collector daemon** — a background `Thread` that samples `os.getloadavg()` and `/proc/meminfo` every 2 seconds, writing rows into the `system_telemetry` PostgreSQL table.
2. **Flask API** — three routes:
   - `GET /` — health check
   - `GET /api/load` — returns the latest DB row as JSON (consumed by `web-dashboard`)
   - `GET /metrics` — returns live system stats in Prometheus exposition format (scraped by Prometheus)

The collector reads from the host's `/proc` through the Docker bind — this only produces meaningful data when the container is running on a Linux host.

`dashboard.py` is a bare `http.server` wrapper: every HTTP request fetches `http://telemetry-app:5000/api/load` and renders the JSON as HTML. It has no state of its own.

Both `telemetry-app` and `web-dashboard` use the same `Dockerfile` (Python 3.11-slim + psycopg2-binary + flask); `compose.yaml` overrides the `command` to select which script runs.

## Volumes

| Volume | Used by | Contents |
|---|---|---|
| `pgdata` | metrics-db | PostgreSQL data directory |
| `promdata` | prometheus | Prometheus TSDB |
| `grafanadata` | grafana | Grafana config, dashboards, datasources |

`app.py` and `dashboard.py` are bind-mounted into their containers, so editing them on the host takes effect after `docker compose restart <service>` — no rebuild needed.

## Database

- **Host**: `metrics-db` (Docker internal hostname)
- **DB**: `telemetry`, **User**: `postgres`, **Password**: `postgres_password`
- **Table**: `system_telemetry(id, timestamp, load_1min, load_5min, load_15min)`

To connect interactively:
```bash
docker compose exec metrics-db psql -U postgres -d telemetry
```

## Permissions

This is a local homelab environment. Claude has blanket approval to:

- Read and edit any file in this repository
- Create new files and directories
- Edit `Dockerfile` and `compose.yaml`
- Run `docker compose` commands (build, up, down, restart, logs, exec, ps)
- Run shell commands for verification and testing (curl, grep, find, python3, bash, etc.)
- Restart or rebuild containers after making changes
