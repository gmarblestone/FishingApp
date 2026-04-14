#!/usr/bin/with-contenv bashio

AREA=$(bashio::config 'area')
REFRESH_HOURS=$(bashio::config 'refresh_hours')
REPORT_PATH=$(bashio::config 'report_path')

HA_TOKEN="${SUPERVISOR_TOKEN}"
HA_API="http://supervisor/core/api"

bashio::log.info "============================================"
bashio::log.info "Fishing Forecast Add-on starting"
bashio::log.info "Area: ${AREA}"
bashio::log.info "Refresh hours: ${REFRESH_HOURS}"
bashio::log.info "Report path: ${REPORT_PATH}"
bashio::log.info "============================================"

mkdir -p "$(dirname "${REPORT_PATH}")" 2>/dev/null || true
mkdir -p /app/www /run/nginx

# ── Write a loading page so nginx has something to show immediately ──────────

cat > /app/www/index.html << 'LOADING'
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Fishing Forecast</title>
<style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background:#f0f4f8;}
.box{text-align:center;padding:40px;background:white;border-radius:16px;box-shadow:0 2px 8px rgba(0,0,0,0.1);}
h1{color:#0c4a6e;margin-bottom:8px;} p{color:#64748b;}</style></head>
<body><div class="box"><h1>🎣 Fishing Forecast</h1><p>Loading forecast data...</p><p>This page will refresh automatically.</p>
<script>setTimeout(()=>location.reload(),15000)</script></div></body></html>
LOADING

bashio::log.info "Loading page written to /app/www/index.html"

# ── Start nginx FIRST so ingress works immediately ───────────────────────────

bashio::log.info "Starting nginx on port 5055..."
nginx &
NGINX_PID=$!
sleep 1

if kill -0 "${NGINX_PID}" 2>/dev/null; then
    bashio::log.info "nginx started (PID ${NGINX_PID})"
else
    bashio::log.error "nginx failed to start!"
fi

# ── Helper: run forecast and push sensors ────────────────────────────────────

run_forecast() {
    bashio::log.info "Running forecast for ${AREA}..."

    # Test Python works
    bashio::log.info "Testing Python..."
    python3 --version 2>&1 | while read -r line; do bashio::log.info "  ${line}"; done

    # Test imports
    bashio::log.info "Testing imports..."
    cd /app && python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from fishing_forecast.config import AREAS
    print('Config OK — areas: ' + ', '.join(AREAS.keys()))
except Exception as e:
    print('Import error: ' + str(e))
    raise
" 2>&1 | while read -r line; do bashio::log.info "  ${line}"; done

    # Generate HTML report directly (simpler, avoids JSON escaping issues)
    bashio::log.info "Generating forecast and report..."
    cd /app && python3 -c "
import sys, traceback
sys.path.insert(0, '.')
try:
    from fishing_forecast.scorer import generate_forecast
    from integrations.html_report import generate_html_string
    print('Fetching data...')
    forecast = generate_forecast('${AREA}')
    print('Scoring complete — ' + str(len(forecast.days)) + ' days')
    html = generate_html_string(forecast)
    with open('${REPORT_PATH}', 'w') as f:
        f.write(html)
    with open('/app/www/index.html', 'w') as f:
        f.write(html)
    print('Report written')
except Exception as e:
    print('ERROR: ' + str(e))
    traceback.print_exc()
    sys.exit(1)
" 2>&1 | while read -r line; do bashio::log.info "  ${line}"; done

    if [ $? -ne 0 ]; then
        bashio::log.error "Forecast generation failed"
        return 1
    fi

    # Push sensors to HA
    bashio::log.info "Pushing sensors to Home Assistant..."
    cd /app && python3 -c "
import sys, json, traceback
sys.path.insert(0, '.')
try:
    from fishing_forecast.scorer import generate_forecast
    forecast = generate_forecast('${AREA}')
    from push_sensors import push_sensors
    import os
    ha_token = os.environ.get('SUPERVISOR_TOKEN', '')
    ha_api = 'http://supervisor/core/api'
    push_sensors(forecast.to_dict(), ha_api, ha_token)
except Exception as e:
    print('Sensor push error: ' + str(e))
    traceback.print_exc()
" 2>&1 | while read -r line; do bashio::log.info "  ${line}"; done

    bashio::log.info "Forecast complete"
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

bashio::log.info "Running initial forecast..."
run_forecast || bashio::log.warning "Initial forecast failed — will retry at next scheduled refresh"

# ── Main loop ────────────────────────────────────────────────────────────────

bashio::log.info "Entering main loop — checking every 30 minutes"
last_run_hour=""

while true; do
    current_hour=$(date +%H | sed 's/^0//')

    if is_refresh_hour && [ "${current_hour}" != "${last_run_hour}" ]; then
        run_forecast && last_run_hour="${current_hour}" || bashio::log.warning "Scheduled forecast failed"
    fi

    # Make sure nginx is still running
    if ! kill -0 "${NGINX_PID}" 2>/dev/null; then
        bashio::log.warning "nginx died — restarting..."
        nginx &
        NGINX_PID=$!
    fi

    sleep 1800
done
