#!/bin/bash
set -o pipefail

log() { echo "[INFO]  $(date '+%H:%M:%S') $*"; }
warn() { echo "[WARN]  $(date '+%H:%M:%S') $*"; }
err() { echo "[ERROR] $(date '+%H:%M:%S') $*"; }

log "============================================"
log "Fishing Forecast Add-on starting"
log "PID $$, user $(whoami)"
log "============================================"

# ── Debug: check for supervisor token in various locations ───────────────────
log "ENV SUPERVISOR_TOKEN length: ${#SUPERVISOR_TOKEN}"
if [ -f /run/s6/container_environment/SUPERVISOR_TOKEN ]; then
  S6_TOKEN=$(cat /run/s6/container_environment/SUPERVISOR_TOKEN)
  log "s6 file token length: ${#S6_TOKEN}"
  export SUPERVISOR_TOKEN="${S6_TOKEN}"
fi
# List env vars related to supervisor (redacted)
env | grep -i 'supervi\|hassio\|token' | sed 's/=.*/=<redacted>/' | while read -r line; do log "  env: $line"; done

# ── Read add-on options ──────────────────────────────────────────────────────

OPTIONS="/data/options.json"
if [ ! -f "$OPTIONS" ]; then
  err "Missing $OPTIONS — add-on options not rendered by supervisor?"
  err "Listing /data:"
  ls -la /data/ 2>&1 || true
  # Fall back to defaults so nginx at least starts
  AREA="matagorda"
  REFRESH_HOURS="5,12"
  REPORT_PATH="/config/www/fishing_forecast.html"
else
  AREA=$(jq -r '.area // "matagorda"' "$OPTIONS")
  REFRESH_HOURS=$(jq -r '.refresh_hours // "5,12"' "$OPTIONS")
  REPORT_PATH=$(jq -r '.report_path // "/config/www/fishing_forecast.html"' "$OPTIONS")
  log "Options loaded: area=${AREA} refresh=${REFRESH_HOURS}"
fi

# Use INGRESS_PORT if supervisor sets it, else fall back to config default
PORT="${INGRESS_PORT:-5055}"
log "Ingress port: ${PORT}"

HA_TOKEN="${SUPERVISOR_TOKEN:-}"
if [ -n "$HA_TOKEN" ]; then
  log "SUPERVISOR_TOKEN set (${#HA_TOKEN} chars)"
else
  warn "SUPERVISOR_TOKEN is EMPTY — sensor push will fail (401)"
  warn "Ensure homeassistant_api: true in config.yaml"
fi

mkdir -p "$(dirname "${REPORT_PATH}")" 2>/dev/null || true
mkdir -p /app/www /run/nginx

# ── Write loading page ───────────────────────────────────────────────────────

cat > /app/www/index.html << 'LOADING'
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Fishing Forecast</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f0f4f8;}
.box{text-align:center;padding:40px;background:white;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,0.1);}
h1{color:#0c4a6e;margin-bottom:8px;} p{color:#64748b;}</style></head>
<body><div class="box"><h1>🎣 Fishing Forecast</h1><p>Loading forecast data...</p><p>This page will refresh automatically.</p>
<script>setTimeout(()=>location.reload(),15000)</script></div></body></html>
LOADING
log "Loading page written"

# ── Kill any stale nginx from previous run ───────────────────────────────────

if command -v pkill >/dev/null 2>&1; then
  pkill -f "nginx" 2>/dev/null || true
  sleep 1
fi
# Verify port is free
if command -v ss >/dev/null 2>&1; then
  if ss -tlnp 2>/dev/null | grep -q ":${PORT} "; then
    warn "Port ${PORT} still in use after cleanup!"
    ss -tlnp 2>/dev/null | grep ":${PORT} " || true
  else
    log "Port ${PORT} is free"
  fi
fi

# ── Configure and start nginx ────────────────────────────────────────────────

if ! command -v nginx >/dev/null 2>&1; then
  err "nginx not installed!"
  exit 1
fi

# Inject actual port into nginx config
sed -i "s/__PORT__/${PORT}/" /etc/nginx/nginx.conf
log "nginx config: port set to ${PORT}"

# Test config
log "Testing nginx config..."
nginx -t 2>&1 | while IFS= read -r line; do log "  $line"; done

# Start nginx (daemon off is in config, so it stays foreground-ish)
log "Starting nginx..."
nginx &
NGINX_PID=$!
sleep 2

if kill -0 "${NGINX_PID}" 2>/dev/null; then
  log "nginx running (PID ${NGINX_PID})"
else
  err "nginx FAILED to start!"
  # Try to see what went wrong
  cat /var/log/nginx/error.log 2>/dev/null || true
  err "Falling back to python3 http.server on port ${PORT}"
  cd /app/www && python3 -m http.server "${PORT}" --bind 0.0.0.0 &
  NGINX_PID=$!
  sleep 1
  if kill -0 "${NGINX_PID}" 2>/dev/null; then
    log "Python fallback server running (PID ${NGINX_PID})"
  else
    err "Fallback server also failed! Ingress will 502."
  fi
fi

# ── Start refresh API server ────────────────────────────────────────────────

log "Starting refresh API server..."
python3 /app/refresh_server.py &
REFRESH_PID=$!
sleep 1
if kill -0 "${REFRESH_PID}" 2>/dev/null; then
  log "Refresh server running (PID ${REFRESH_PID})"
else
  warn "Refresh server failed to start"
fi

# ── Graceful shutdown ────────────────────────────────────────────────────────

shutdown() {
  log "Shutdown requested..."
  kill -TERM "${NGINX_PID}" 2>/dev/null || true
  kill -TERM "${REFRESH_PID}" 2>/dev/null || true
  wait "${NGINX_PID}" 2>/dev/null || true
  wait "${REFRESH_PID}" 2>/dev/null || true
  exit 0
}
trap shutdown INT TERM

# ── Forecast helper ───────────────────────────────────────────────────────────

run_forecast() {
    log "Running forecast for ${AREA}..."
    touch /tmp/refresh_running
    cd /app && python3 -c "
import sys, traceback, os
sys.path.insert(0, '.')
try:
    from fishing_forecast.scorer import generate_forecast
    from integrations.html_report import generate_html_string
    from integrations.image_report import generate_image, generate_detail_image
    print('Fetching data...')
    forecast = generate_forecast('${AREA}')
    print('Scoring complete — ' + str(len(forecast.days)) + ' days')
    html = generate_html_string(forecast)
    with open('${REPORT_PATH}', 'w') as f:
        f.write(html)
    with open('/app/www/index.html', 'w') as f:
        f.write(html)
    print('HTML report written')
    # Generate JPG images
    base = os.path.dirname('${REPORT_PATH}')
    # 7-day overview
    generate_image(forecast, os.path.join(base, 'fishing_forecast.jpg'))
    print('7-day JPG written')
    # Today detail
    generate_detail_image(forecast, [0], 'Today\\'s Fishing Report', os.path.join(base, 'fishingreport_today.jpg'))
    print('Today JPG written')
    # Tomorrow detail
    if len(forecast.days) > 1:
        generate_detail_image(forecast, [1], 'Tomorrow\\'s Fishing Report', os.path.join(base, 'fishingreport_tomorrow.jpg'))
        print('Tomorrow JPG written')
    # 3-day detail
    indices = list(range(min(3, len(forecast.days))))
    generate_detail_image(forecast, indices, '3-Day Fishing Report', os.path.join(base, 'fishingreport_threeday.jpg'))
    print('3-day JPG written')
except Exception as e:
    print('ERROR: ' + str(e))
    traceback.print_exc()
    sys.exit(1)
" 2>&1 | while read -r line; do log "  ${line}"; done

    if [ $? -ne 0 ]; then
        err "Forecast generation failed"
        rm -f /tmp/refresh_running
        return 1
    fi

    # Push sensors to HA
    log "Pushing sensors..."
    cd /app && python3 -c "
import sys, traceback, os
sys.path.insert(0, '.')
token = os.environ.get('SUPERVISOR_TOKEN', '')
print('Token length: ' + str(len(token)))
if not token:
    print('SUPERVISOR_TOKEN is empty - skipping sensor push')
    sys.exit(0)
try:
    from fishing_forecast.scorer import generate_forecast
    forecast = generate_forecast('${AREA}')
    from push_sensors import push_sensors
    push_sensors(forecast.to_dict(), 'http://supervisor/core/api', token)
except Exception as e:
    print('Sensor push error: ' + str(e))
    traceback.print_exc()
" 2>&1 | while read -r line; do log "  ${line}"; done

    log "Forecast complete"
    rm -f /tmp/refresh_running
}

# ── Helper: check if current hour is a refresh hour ──────────────────────────

is_refresh_hour() {
    current_hour=$(date +%H | sed 's/^0//')
    IFS=',' read -ra hours <<< "${REFRESH_HOURS}"
    for h in "${hours[@]}"; do
        h=$(echo "$h" | tr -d ' ')
        if [ "${current_hour}" = "${h}" ]; then
            return 0
        fi
    done
    return 1
}

# ── Initial run ──────────────────────────────────────────────────────────────

log "Running initial forecast..."
run_forecast || warn "Initial forecast failed — will retry at next refresh"

# ── Main loop ────────────────────────────────────────────────────────────────

log "Entering main loop"
last_run_hour=""

while true; do
    sleep 5

    current_hour=$(date +%H | sed 's/^0//')

    # Check for manual refresh trigger
    if [ -f /tmp/refresh_trigger ]; then
        log "Manual refresh triggered!"
        rm -f /tmp/refresh_trigger
        run_forecast && last_run_hour="${current_hour}" || warn "Triggered forecast failed"
    fi

    # Scheduled refresh at configured hours
    if is_refresh_hour && [ "${current_hour}" != "${last_run_hour}" ]; then
        run_forecast && last_run_hour="${current_hour}" || warn "Scheduled forecast failed"
    fi

    # Keep nginx alive
    if ! kill -0 "${NGINX_PID}" 2>/dev/null; then
        warn "nginx died — restarting..."
        nginx &
        NGINX_PID=$!
    fi

    # Keep refresh server alive
    if ! kill -0 "${REFRESH_PID}" 2>/dev/null; then
        warn "Refresh server died — restarting..."
        python3 /app/refresh_server.py &
        REFRESH_PID=$!
    fi
done
