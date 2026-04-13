#!/usr/bin/with-contenv bashio
# ─────────────────────────────────────────────────────────────────────────────
# Fishing Forecast Add-on — Entry Point
#
# Reads config from HA add-on options, runs the forecast engine,
# sets sensors via HA REST API, writes HTML report, then sleeps
# until next refresh.
# ─────────────────────────────────────────────────────────────────────────────

set -e

AREA=$(bashio::config 'area')
REFRESH_HOURS=$(bashio::config 'refresh_hours')
REPORT_PATH=$(bashio::config 'report_path')

# HA Supervisor token is auto-injected by the add-on runtime
HA_TOKEN="${SUPERVISOR_TOKEN}"
HA_API="http://supervisor/core/api"

bashio::log.info "Fishing Forecast starting — area: ${AREA}"
bashio::log.info "Refresh hours: ${REFRESH_HOURS}"
bashio::log.info "Report path: ${REPORT_PATH}"

# Ensure www directory exists
mkdir -p "$(dirname "${REPORT_PATH}")"

# ── Helper: run forecast and push sensors ────────────────────────────────────

run_forecast() {
    bashio::log.info "Running forecast for ${AREA}..."

    # Generate forecast JSON
    FORECAST=$(cd /app && python3 -c "
import json, sys
sys.path.insert(0, '.')
from fishing_forecast.scorer import generate_forecast
result = generate_forecast('${AREA}')
print(json.dumps(result.to_dict()))
")

    if [ -z "${FORECAST}" ]; then
        bashio::log.error "Forecast returned empty — check API connectivity"
        return 1
    fi

    bashio::log.info "Forecast generated, pushing sensors..."

    # Push sensors to HA
    cd /app && python3 -c "
import json, sys, os
sys.path.insert(0, '.')

ha_token = os.environ.get('SUPERVISOR_TOKEN', '')
ha_api = 'http://supervisor/core/api'
forecast_json = '''${FORECAST}'''

from push_sensors import push_sensors
push_sensors(json.loads(forecast_json), ha_api, ha_token)
"

    # Generate HTML report
    cd /app && python3 -c "
import sys
sys.path.insert(0, '.')
from fishing_forecast.scorer import generate_forecast
from integrations.html_report import generate_html_string
forecast = generate_forecast('${AREA}')
html = generate_html_string(forecast)
with open('${REPORT_PATH}', 'w') as f:
    f.write(html)
print('Report written to ${REPORT_PATH}')
"

    bashio::log.info "Forecast complete — sensors updated, report written"
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

run_forecast || bashio::log.warning "Initial forecast failed — will retry at next refresh"

# ── Main loop: check every 30 minutes, run on refresh hours ──────────────────

last_run_hour=""

while true; do
    current_hour=$(date +%H | sed 's/^0//')

    if is_refresh_hour && [ "${current_hour}" != "${last_run_hour}" ]; then
        run_forecast && last_run_hour="${current_hour}" || bashio::log.warning "Scheduled forecast failed"
    fi

    sleep 1800  # Check every 30 minutes
done
