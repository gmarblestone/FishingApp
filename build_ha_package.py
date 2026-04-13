"""Build fishing_forecast_ha.tar.gz for Home Assistant AppDaemon deployment."""

import tarfile
import io
from pathlib import Path

ROOT = Path(__file__).parent
OUT = ROOT / "fishing_forecast_ha.tar.gz"

APPS_YAML = """\
fishing_forecast:
  module: fishing_forecast.fishing_app
  class: FishingForecastApp
  area: matagorda
  report_path: /config/www/fishing_forecast.html
  refresh_times:
    - "05:00:00"
    - "12:00:00"
"""

FILES = [
    ("fishing_forecast/__init__.py",    ROOT / "fishing_forecast" / "__init__.py"),
    ("fishing_forecast/config.py",      ROOT / "fishing_forecast" / "config.py"),
    ("fishing_forecast/fetcher.py",     ROOT / "fishing_forecast" / "fetcher.py"),
    ("fishing_forecast/models.py",      ROOT / "fishing_forecast" / "models.py"),
    ("fishing_forecast/scorer.py",      ROOT / "fishing_forecast" / "scorer.py"),
    ("fishing_forecast/fishing_app.py", ROOT / "fishing_forecast" / "fishing_app.py"),
    ("integrations/__init__.py",        ROOT / "integrations" / "__init__.py"),
    ("integrations/html_report.py",     ROOT / "integrations" / "html_report.py"),
]

with tarfile.open(OUT, "w:gz") as tar:
    # Add apps.yaml at root
    data = APPS_YAML.encode()
    info = tarfile.TarInfo(name="apps.yaml")
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))

    # Add Python files
    for arc_name, src_path in FILES:
        tar.add(str(src_path), arcname=arc_name)

print(f"Built: {OUT}")
print(f"Size: {OUT.stat().st_size / 1024:.0f} KB")
print()
print("Install on HA terminal:")
print("  1. Copy fishing_forecast_ha.tar.gz to /config/")
print("  2. Run:")
print("     mkdir -p /config/www")
print("     cd /config/apps")
print("     tar xzf /config/fishing_forecast_ha.tar.gz")
print("  3. Restart AppDaemon")
