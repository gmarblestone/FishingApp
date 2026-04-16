"""Tiny HTTP server that triggers an immediate forecast refresh."""
import http.server
import json
import os
import sys

sys.path.insert(0, "/app")

PORT = 8099
TRIGGER_FILE = "/tmp/refresh_trigger"
LOCK_FILE = "/tmp/refresh_running"


class RefreshHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/refresh":
            if os.path.exists(LOCK_FILE):
                self._respond(429, {"status": "busy", "message": "Refresh already in progress"})
                return
            try:
                open(TRIGGER_FILE, "w").close()
                self._respond(200, {"status": "triggered"})
            except Exception as e:
                self._respond(500, {"status": "error", "message": str(e)})
        else:
            self._respond(404, {"status": "not_found"})

    def _respond(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        print(f"[REFRESH] {args[0]}", flush=True)


if __name__ == "__main__":
    server = http.server.HTTPServer(("127.0.0.1", PORT), RefreshHandler)
    print(f"[REFRESH] Listening on 127.0.0.1:{PORT}", flush=True)
    server.serve_forever()
