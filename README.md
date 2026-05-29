# Unified Lab Infrastructure

A multi-tier, containerized monitoring and observability command center for the devops-box.

## Services
- **telemetry-app**: Python daemon collecting system load metrics.
- **metrics-db**: PostgreSQL storage for persistent data.
- **prometheus**: Time-series metrics engine.
- **grafana**: Enterprise dashboarding and visualization.
- **web-dashboard**: Custom front-end interface.

## Quick Start
1. Ensure Docker and Docker Compose are installed.
2. Clone the repo: `git clone <your-repo-url>`
3. Bring the stack up: `docker compose up -d`
4. Access Grafana at: `http://devops-box:3001`

## Documentation
- Metrics are scraped every 5s from `telemetry-app:5000/metrics`.
- All persistent data is stored in Docker volumes (pgdata, promdata, grafanadata).
