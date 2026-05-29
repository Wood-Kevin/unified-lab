from http.server import SimpleHTTPRequestHandler, HTTPServer
import urllib.request
import json

PORT = 8080
API_URL = "http://telemetry-app:5000/api/load"

class DashboardHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        try:
            with urllib.request.urlopen(API_URL, timeout=5) as response:
                data = json.loads(response.read().decode())
                content = f"<h1>Metrics</h1><pre>{json.dumps(data, indent=2)}</pre>"
        except Exception as e:
            content = f"<h1>Error</h1><p>{str(e)}</p>"
            
        self.wfile.write(content.encode())

if __name__ == "__main__":
    HTTPServer(('0.0.0.0', PORT), DashboardHandler).serve_forever()