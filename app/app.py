import os
import time
import psycopg2
from threading import Thread
from flask import Flask, jsonify

app = Flask(__name__)

# Connection string pointing directly to the internal Docker network container name
DB_DSN = "host=metrics-db dbname=telemetry user=postgres password=postgres_password"

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
            conn.commit()
            cursor.close()
            conn.close()
            print("Successfully connected to PostgreSQL. Storage table is ready.", flush=True)
            break
        except psycopg2.OperationalError:
            print("Waiting for database tier to accept connections...", flush=True)
            time.sleep(2)

    # Core collection loop
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
        # Sample the live kernel metrics directly for the scraper
        load_1, load_5, load_15 = os.getloadavg()
        
        output = (
            "# HELP system_load_1min Linux kernel 1-minute load average\n"
            "# TYPE system_load_1min gauge\n"
            f"system_load_1min {load_1}\n\n"
            "# HELP system_load_5min Linux kernel 5-minute load average\n"
            "# TYPE system_load_5min gauge\n"
            f"system_load_5min {load_5}\n\n"
            "# HELP system_load_15min Linux kernel 15-minute load average\n"
            "# TYPE system_load_15min gauge\n"
            f"system_load_15min {load_15}\n"
        )
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