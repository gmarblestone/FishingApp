#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_ha.sh — Deploy Fishing Forecast into Home Assistant AppDaemon
#
# Run from the HA terminal (SSH or Terminal add-on):
#   1. Copy FishingApp/ to /config/  (Samba, SCP, or File Editor)
#   2. cd /config/FishingApp
#   3. bash deploy_ha.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

# ── Auto-detect AppDaemon apps directory ─────────────────────────────────────
if [ -d "/config/apps" ]; then
    APPS_DIR="/config/apps"
elif [ -d "/config/appdaemon/apps" ]; then
    APPS_DIR="/config/appdaemon/apps"
else
    APPS_DIR="/config/apps"
fi

FF_DIR="$APPS_DIR/fishing_forecast"
INT_DIR="$APPS_DIR/integrations"
WWW_DIR="/config/www"
CONFIG_YAML="/config/configuration.yaml"

# Where am I?
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🎣 Fishing Forecast — HA Deploy"
echo "================================"
echo "Source: $SCRIPT_DIR"
echo ""

# ── Verify we're in the right place ──────────────────────────────────────────

if [ ! -f "$SCRIPT_DIR/fishing_forecast/fishing_app.py" ]; then
    echo "❌ Can't find fishing_forecast/fishing_app.py"
    echo "   Run this script from the FishingApp directory."
    exit 1
fi

# ── Create directories ───────────────────────────────────────────────────────

echo "📁 Creating directories..."
mkdir -p "$FF_DIR"
mkdir -p "$INT_DIR"
mkdir -p "$WWW_DIR"

# ── Copy core engine ─────────────────────────────────────────────────────────

echo "📦 Copying fishing_forecast/ ..."
cp "$SCRIPT_DIR/fishing_forecast/__init__.py"    "$FF_DIR/"
cp "$SCRIPT_DIR/fishing_forecast/config.py"      "$FF_DIR/"
cp "$SCRIPT_DIR/fishing_forecast/fetcher.py"     "$FF_DIR/"
cp "$SCRIPT_DIR/fishing_forecast/models.py"      "$FF_DIR/"
cp "$SCRIPT_DIR/fishing_forecast/scorer.py"      "$FF_DIR/"
cp "$SCRIPT_DIR/fishing_forecast/fishing_app.py" "$FF_DIR/"
cp "$SCRIPT_DIR/fishing_forecast/apps.yaml"      "$FF_DIR/"

echo "📦 Copying integrations/ ..."
cp "$SCRIPT_DIR/integrations/__init__.py"        "$INT_DIR/"
cp "$SCRIPT_DIR/integrations/html_report.py"     "$INT_DIR/"

# ── Add panel_iframe to configuration.yaml ───────────────────────────────────

if [ -f "$CONFIG_YAML" ]; then
    if grep -q "panel_iframe:" "$CONFIG_YAML"; then
        if grep -q "fishing_forecast:" "$CONFIG_YAML"; then
            echo "✅ panel_iframe already configured"
        else
            echo "📝 Adding fishing_forecast to existing panel_iframe..."
            sed -i '/^panel_iframe:/a\  fishing_forecast:\n    title: "Fishing Forecast"\n    icon: mdi:fish\n    url: "/local/fishing_forecast.html"' "$CONFIG_YAML"
        fi
    else
        echo "📝 Adding panel_iframe to configuration.yaml..."
        cat >> "$CONFIG_YAML" << 'EOF'

panel_iframe:
  fishing_forecast:
    title: "Fishing Forecast"
    icon: mdi:fish
    url: "/local/fishing_forecast.html"
EOF
    fi
else
    echo "⚠️  $CONFIG_YAML not found — add panel_iframe manually"
fi

# ── Add requests to AppDaemon packages if appdaemon.yaml exists ──────────────

AD_YAML="/config/appdaemon/appdaemon.yaml"
if [ -f "$AD_YAML" ]; then
    if grep -q "requests" "$AD_YAML"; then
        echo "✅ requests already in AppDaemon packages"
    else
        echo "⚠️  Add 'requests' to AppDaemon python_packages in add-on config"
        echo "   Settings → Add-ons → AppDaemon → Configuration → python_packages"
        echo "   Add:  - requests"
    fi
fi

# ── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo "================================"
echo "✅ Deploy complete!"
echo ""
echo "Files installed:"
echo "  $FF_DIR/"
ls -la "$FF_DIR/"
echo ""
echo "  $INT_DIR/"
ls -la "$INT_DIR/"
echo ""
echo "Next steps:"
echo "  1. Make sure 'requests' is in AppDaemon python_packages"
echo "     Settings → Add-ons → AppDaemon → Configuration"
echo "     python_packages:"
echo "       - requests"
echo ""
echo "  2. Restart AppDaemon"
echo "     Settings → Add-ons → AppDaemon → Restart"
echo ""
echo "  3. Restart HA core (for panel_iframe sidebar)"
echo "     Settings → System → Restart"
echo ""
echo "  4. Add dashboard card (optional)"
echo "     Paste homeassistant/dashboard.yaml into Lovelace raw config"
echo ""
echo "  5. Check AppDaemon logs for 'Fishing Forecast initializing'"
echo "     Settings → Add-ons → AppDaemon → Log"
