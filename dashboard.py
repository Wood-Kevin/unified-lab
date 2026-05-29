from http.server import SimpleHTTPRequestHandler, HTTPServer
import urllib.request
import json

PORT = 8080
API_URL = "http://telemetry-app:5000/api/metrics"

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            
            # Fetch structured JSON metrics from our middle-tier API container
            ui_rows = ""
            try:
                with urllib.request.urlopen(API_URL, timeout=3) as response:
                    data = json.loads(response.read().decode("utf-8"))
                    
                    if isinstance(data, list):
                        for entry in data:
                            ui_rows += f"[API METRIC] Time: {entry['timestamp']} | 1-Min CPU Load: {entry['load']}\n"
                    else:
                        ui_rows = f"API Error: {data.get('error')}"
            except Exception as e:
                ui_rows = f"Failed to reach API gateway tier: {e}"

            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Secure 3-Tier Stack</title>
                <style>
                    body {{ font-family: Arial, sans-serif; background-color: #2c3e50; color: #ecf0f1; padding: 20px; }}
                    h1 {{ color: #e74c3c; border-bottom: 2px solid #34495e; padding-bottom: 10px; }}
                    pre {{ background-color: #1a252f; color: #3498db; padding: 15px; border-radius: 5px; border: 1px solid #34495e; font-size: 14px; line-height: 1.5; }}
                    .refresh {{ color: #95a5a6; font-size: 12px; }}
                </style>
                <meta http-equiv="refresh" content="5">
            </head>
            <body>
                <h1>Node 1 Multi-Network Live Stream</h1>
                <p class="refresh">Fetching structured API payload over isolated virtual network every 5 seconds</p>
                <pre>{ui_rows if ui_rows else "Awaiting API payload stream..."}</pre>
            </body>
            </html>
            """
            self.wfile.write(html.encode("utf-8"))
        else:
            self.send_error(404, "File Not Found")

def run():
    print(f"Dashboard web server booting on port {PORT}...")
    server = HTTPServer(('0.0.0.0', PORT), DashboardHandler)
    server.serve_forever()

if __name__ == "__main__":
    run()