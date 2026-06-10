import os
import time
import psycopg2
from threading import Thread
from flask import Flask, jsonify, g, request
from prometheus_client import Counter, Histogram, Gauge, generate_latest

app = Flask(__name__)

# Connection string pointing directly to the internal Docker network container name
DB_DSN = "host=metrics-db dbname=telemetry user=postgres password=postgres_password"

# ------------------------------------------------------------------
# PROMETHEUS METRICS
# ------------------------------------------------------------------
flask_requests_total = Counter(
    'flask_requests_total',
    'Total number of Flask HTTP requests',
    ['route', 'http_status_code']
)
flask_request_duration_seconds = Histogram(
    'flask_request_duration_seconds',
    'Flask HTTP request duration in seconds',
    ['route']
)
db_connected = Gauge(
    'db_connected',
    'Set to 1 if a DB connection succeeds, 0 otherwise'
)
collector_last_write_unix = Gauge(
    'collector_last_write_unix',
    'Unix timestamp of the last successful collector thread insert'
)
collector_rows_total = Counter(
    'collector_rows_total',
    'Total rows successfully inserted by the collector thread'
)
db_row_count = Gauge(
    'db_row_count',
    'Total number of rows in system_telemetry'
)
db_size_bytes = Gauge(
    'db_size_bytes',
    'Total size of the telemetry database in bytes'
)


# ------------------------------------------------------------------
# REQUEST INSTRUMENTATION HOOKS
# ------------------------------------------------------------------
@app.before_request
def _start_timer():
    g.start_time = time.time()


@app.after_request
def _record_request_metrics(response):
    duration = time.time() - g.start_time
    flask_request_duration_seconds.labels(route=request.path).observe(duration)
    flask_requests_total.labels(route=request.path, http_status_code=str(response.status_code)).inc()
    return response


# ------------------------------------------------------------------
# BACKEND COMPONENT: The Data Collection Worker Thread
# ------------------------------------------------------------------
def metrics_collector_daemon():
    """Background worker that samples system load and commits it to PostgreSQL."""
    print("Initializing background metrics collector daemon...", flush=True)

    # Simple retry loop to wait for PostgreSQL container to finish booting up
    while True:
        try:
            conn = psycopg2.connect(DB_DSN)
            cursor = conn.cursor()
            # Ensure our database table exists before we start recording
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_telemetry (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    load_1min REAL,
                    load_5min REAL,
                    load_15min REAL
                );
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp
                ON system_telemetry(timestamp);
            """)
            conn.commit()
            cursor.close()
            conn.close()
            print("Successfully connected to PostgreSQL. Storage table is ready.", flush=True)
            break
        except psycopg2.OperationalError:
            print("Waiting for database tier to accept connections...", flush=True)
            time.sleep(2)

    # Core collection loop
    last_prune = time.time()
    while True:
        try:
            # Grab native Linux kernel load averages
            load_1, load_5, load_15 = os.getloadavg()

            # Connect and insert snapshots into the DB
            conn = psycopg2.connect(DB_DSN)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO system_telemetry (load_1min, load_5min, load_15min)
                VALUES (%s, %s, %s);
                """,
                (load_1, load_5, load_15)
            )
            conn.commit()
            cursor.close()
            conn.close()

            collector_rows_total.inc()
            collector_last_write_unix.set(time.time())

            # Prune rows older than 30 days once per hour
            if time.time() - last_prune >= 3600:
                try:
                    conn = psycopg2.connect(DB_DSN)
                    cursor = conn.cursor()
                    cursor.execute(
                        "DELETE FROM system_telemetry WHERE timestamp < NOW() - INTERVAL '30 days';"
                    )
                    conn.commit()
                    cursor.close()
                    conn.close()
                    print("Retention pruning complete: removed rows older than 30 days.", flush=True)
                except Exception as e:
                    print(f"Retention pruning error: {e}", flush=True)
                last_prune = time.time()

        except Exception as e:
            print(f"Error in metrics collector daemon: {e}", flush=True)

        # Sample the host system resources every 2 seconds
        time.sleep(2)


# ------------------------------------------------------------------
# API COMPONENT: HTTP Endpoints
# ------------------------------------------------------------------

@app.route('/')
def index():
    return jsonify({"status": "healthy", "service": "telemetry-api-engine"}), 200


@app.route('/api/load')
def get_json_load():
    """Serves the latest database snapshot as JSON for your web dashboard UI."""
    try:
        conn = psycopg2.connect(DB_DSN)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, load_1min, load_5min, load_15min
            FROM system_telemetry
            ORDER BY id DESC LIMIT 1;
        """)
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            return jsonify({
                "timestamp": str(row[0]),
                "load_1min": row[1],
                "load_5min": row[2],
                "load_15min": row[3]
            }), 200
        return jsonify({"error": "No metrics recorded yet"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/metrics')
def metrics():
    """Serves raw real-time metrics in the standard Prometheus exposition format."""
    try:
        # 1. Sample the live kernel load metrics
        load_1, load_5, load_15 = os.getloadavg()

        # 2. Extract memory stats directly from the kernel
        mem_total = 0
        mem_available = 0
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if 'MemTotal:' in line:
                    mem_total = int(line.split()[1])
                elif 'MemAvailable:' in line:
                    mem_available = int(line.split()[1])
                # Stop parsing early once we have both values
                if mem_total and mem_available:
                    break

        # Calculate used percentage safely
        mem_pct = ((mem_total - mem_available) / mem_total) * 100 if mem_total else 0

        # 3. Refresh on-scrape gauges
        try:
            conn = psycopg2.connect(DB_DSN)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM system_telemetry;")
            db_row_count.set(cursor.fetchone()[0])
            cursor.execute("SELECT pg_database_size('telemetry');")
            db_size_bytes.set(cursor.fetchone()[0])
            cursor.close()
            conn.close()
            db_connected.set(1)
        except Exception:
            db_connected.set(0)

        # 4. Hand-written exposition text (existing)
        hand_written = (
            "# HELP system_load_1min Linux kernel 1-minute load average\n"
            "# TYPE system_load_1min gauge\n"
            f"system_load_1min {load_1}\n\n"
            "# HELP system_load_5min Linux kernel 5-minute load average\n"
            "# TYPE system_load_5min gauge\n"
            f"system_load_5min {load_5}\n\n"
            "# HELP system_load_15min Linux kernel 15-minute load average\n"
            "# TYPE system_load_15min gauge\n"
            f"system_load_15min {load_15}\n\n"
            "# HELP system_memory_usage_percent Percentage of system memory currently utilized\n"
            "# TYPE system_memory_usage_percent gauge\n"
            f"system_memory_usage_percent {mem_pct:.2f}\n"
        )

        # 5. Combine with prometheus_client generated metrics
        output = hand_written + "\n" + generate_latest().decode('utf-8')
        return output, 200, {'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'}

    except Exception as e:
        return f"Error gathering metrics: {str(e)}", 500


# ------------------------------------------------------------------
# RUNTIME ENGINE INITIALIZATION
# ------------------------------------------------------------------
if __name__ == '__main__':
    # 1. Fire up the background logging worker as a background daemon thread
    worker = Thread(target=metrics_collector_daemon, daemon=True)
    worker.start()

    # 2. Start the Flask HTTP Server on the main thread
    # Binding to 0.0.0.0 lets it accept connections inside the Docker bridge network
    app.run(host='0.0.0.0', port=5000, debug=False)
