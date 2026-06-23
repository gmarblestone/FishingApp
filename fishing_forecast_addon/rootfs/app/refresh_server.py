"""Tiny HTTP server that triggers an immediate forecast refresh."""
import http.server
import json
import os
import sys
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, "/app")

PORT = 8099
TRIGGER_FILE = "/tmp/refresh_trigger"
LOCK_FILE = "/tmp/refresh_running"


class RefreshHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/refresh":
            if os.path.exists(LOCK_FILE):
                self._respond(429, {"status": "busy", "message": "Refresh already in progress"})
                return
            try:
                open(TRIGGER_FILE, "w").close()
                self._respond(200, {"status": "triggered"})
            except Exception as e:
                self._respond(500, {"status": "error", "message": str(e)})
        elif path == "/report":
            area = params.get("area", [None])[0]
            try:
                from fishing_forecast.config import AREAS, DEFAULT_AREA
                from fishing_forecast.scorer import generate_forecast
                from integrations.html_report import generate_html_string

                area_key = area or DEFAULT_AREA
                if area_key not in AREAS:
                    self._respond(400, {"status": "error", "message": f"Unknown area: {area_key}"})
                    return

                forecast = generate_forecast(area_key)
                html = generate_html_string(forecast, area_key)
                self._respond_text(200, html, "text/html; charset=utf-8")
            except Exception as e:
                self._respond(500, {"status": "error", "message": str(e)})
        else:
            self._respond(404, {"status": "not_found"})

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _respond_text(self, code, body, content_type):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, format, *args):
        print(f"[REFRESH] {args[0]}", flush=True)


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), RefreshHandler)
    print(f"[REFRESH] Listening on 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()
