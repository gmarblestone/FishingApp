#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# build_ha_package.sh — Package FishingApp for Home Assistant AppDaemon
#
# Run on your dev machine (Git Bash / WSL / Linux):
#   cd FishingApp
#   bash build_ha_package.sh
#
# Produces: fishing_forecast_ha.tar.gz
#
# Install on HA terminal:
#   cd /config/apps
#   tar xzf /config/fishing_forecast_ha.tar.gz
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$SCRIPT_DIR/fishing_forecast_ha.tar.gz"
STAGE=$(mktemp -d)

echo "🎣 Building HA package..."

# ── Stage files in correct directory structure ───────────────────────────────

mkdir -p "$STAGE/fishing_forecast"
mkdir -p "$STAGE/integrations"

# Core engine
cp "$SCRIPT_DIR/fishing_forecast/__init__.py"    "$STAGE/fishing_forecast/"
cp "$SCRIPT_DIR/fishing_forecast/config.py"      "$STAGE/fishing_forecast/"
cp "$SCRIPT_DIR/fishing_forecast/fetcher.py"     "$STAGE/fishing_forecast/"
cp "$SCRIPT_DIR/fishing_forecast/models.py"      "$STAGE/fishing_forecast/"
cp "$SCRIPT_DIR/fishing_forecast/scorer.py"      "$STAGE/fishing_forecast/"
cp "$SCRIPT_DIR/fishing_forecast/fishing_app.py" "$STAGE/fishing_forecast/"

# HTML report
cp "$SCRIPT_DIR/integrations/__init__.py"        "$STAGE/integrations/"
cp "$SCRIPT_DIR/integrations/html_report.py"     "$STAGE/integrations/"

# Top-level apps.yaml (AppDaemon finds this reliably)
cat > "$STAGE/apps.yaml" << 'YAML'
fishing_forecast:
  module: fishing_forecast.fishing_app
  class: FishingForecastApp
  area: matagorda
  report_path: /config/www/fishing_forecast.html
  refresh_times:
    - "05:00:00"
    - "12:00:00"
YAML

# ── Build archive ────────────────────────────────────────────────────────────

tar czf "$OUT" -C "$STAGE" .
rm -rf "$STAGE"

echo ""
echo "✅ Package built: $OUT"
echo ""
echo "Install on HA:"
echo "  1. Copy fishing_forecast_ha.tar.gz to /config/ (Samba or SCP)"
echo "  2. HA terminal:"
echo "     mkdir -p /config/www"
echo "     cd /config/apps"
echo "     tar xzf /config/fishing_forecast_ha.tar.gz"
echo "  3. Restart AppDaemon"
