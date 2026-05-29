# Infrastructure Documentation: Unified Telemetry Stack
**Project Location:** `~/unified-lab`  
**Host Environment:** `devops-box`  
**Deployment Model:** Docker Compose (Single-Host Bridge Networking)  
**Last Updated:** May 2026

---

## 1. Architectural Overview
This infrastructure implements a modular, self-contained three-tier monitoring and observability platform. The system profiles local host resources directly via the Linux kernel virtual filesystem, persists operational state within a relational data store, and aggregates time-series metrics into a centralized visualization plane.

### Core Architectural Layers
1. **Data Acquisition & API Layer (telemetry-app):** A Flask-based engine executing a dual-purpose architecture. A background daemon thread samples system resources periodically and handles data persistence, while the web thread exposes endpoints for custom application consumers and standardized scrapers.
2. **Time-Series Core (prometheus):** A localized Time-Series Database (TSDB) configured to poll downstream exposition vectors at high frequency.
3. **Visualization Plane (grafana):** An analytics and metric visualization engine rendering point-in-time and historical system behavior.
4. **Relational Storage (metrics-db):** A PostgreSQL backend housing structured long-term historical snapshots of system state.

---

## 2. Network Topology & Port Mapping Matrix
All containers operate on a dedicated internal Docker network bridge. Service discovery relies entirely on embedded Docker DNS using explicit container service names.

| Service Name (DNS Hostname) | Internal Container Port | Exposed Host Port | Transport Protocol | Endpoint Traffic / Function |
| :--- | :--- | :--- | :--- | :--- |
| telemetry-app | 5000 | 5000 | TCP / HTTP | JSON API (/api/load) & PromQL Exposition (/metrics) |
| prometheus | 9090 | 9090 | TCP / HTTP | Prometheus Administrative Web UI & TSDB Query API |
| grafana | 3000 | 3001 | TCP / HTTP | Grafana Web Dashboard User Interface |
| metrics-db | 5432 | None (Isolated) | TCP / PostgreSQL | Internal Database Storage Plane |

---

## 3. Storage Layer & Volume Configurations
Persistent storage, configuration files, and state preservation are mapped deterministically between the host environment and specific container boundaries.

Volume Binding Map Matrix:
Host File/Path              Container Destination                Access Mode
├── ./prometheus.yml   ──>  /etc/prometheus/prometheus.yml      [Read-Only (ro)]
└── Managed Volume      ──>  /var/lib/grafana                    [Read-Write (rw)]


### Critical Architecture Controls
* **Configuration Mapping:** The Prometheus server is rigidly configured via a file-to-file bind mount. It expects the .yml extension (prometheus.yml). Mismatches or directory collisions (e.g., creating a prometheus/ folder) break container runtime initialization.
* **Volume Persistence:** Grafana dashboards and Prometheus time-series indices are stored inside persistent layers to prevent telemetry data degradation across container lifecycles (down / up).

---

## 4. Telemetry Metrics Directory
The application targets host kernel statistics dynamically. Metrics exposed on http://telemetry-app:5000/metrics are formatted under strict Prometheus ASCII exposition standards.

### Exposed Gauges
* **system_load_1min**: Linux kernel 1-minute load average. Tracks CPU thread execution queuing.
* **system_load_5min**: Linux kernel 5-minute load average.
* **system_load_15min**: Linux kernel 15-minute load average.
* **system_memory_usage_percent**: Derived mathematical utility metric calculating current active memory footprint:
  Memory Utilization % = ((MemTotal - MemAvailable) / MemTotal) * 100
  *Source Data: Extracted on demand via raw reads of /proc/meminfo.*

---

## 5. Grafana Panel Dashboard Specifications
The operational dashboard is segmented across multiple visualization primitives optimized for specific tracking signatures.

### Panel 1: Core Processor Demands
* **Type:** Time series
* **Title:** System Load Averages
* **Queries (PromQL):** {__name__=~"system_load_.*"} (Pulls 1, 5, and 15-minute vectors dynamically)
* **Visual Polish:** Line graph, fill opacity 10-20%, Tooltip mode: All, Legend placement: Table / Bottom.

### Panel 2: Momentary Memory Footprint
* **Type:** Gauge
* **Title:** System Memory Usage
* **Query (PromQL):** system_memory_usage_percent
* **Visual Polish:** Min 0, Max 100, Unit: Misc / Percent (0-100). Color thresholds set to green/yellow/red.

### Panel 3: Memory Allocation Timeline
* **Type:** Time series
* **Title:** Memory Utilization Trend
* **Query (PromQL):** system_memory_usage_percent
* **Visual Polish:** Line style with data points enabled, tracking historical micro-fluctuations.

---

## 6. Verification, Validation & Runbook Procedures
To ensure infrastructure performance remains nominal, validation tests can be performed directly via the devops-box terminal interface.

### Phase 1: Local Application Verification
Isolate and verify that the application layer is computing and outputting metrics without error:
```bash
curl http://devops-box:5000/metrics

Expected Result: Clean HTTP 200 payload exhibiting current metric keys and float values.
Phase 2: Scraper Engine Validation

Confirm that the Prometheus indexing agent has successfully discovered and connected to the application target:
Bash

curl -s http://localhost:9090/api/v1/targets

Expected Result: Active rows reporting state as "up". Alternatively, visually inspect http://localhost:9090/targets.
Phase 3: Telemetry Plane Verification

Query the raw database storage to verify Prometheus-to-Grafana readiness:
Bash

curl -s http://localhost:9090/api/v1/label/__name__/values | grep system_memory

Expected Result: Returns entry confirmation string system_memory_usage_percent.