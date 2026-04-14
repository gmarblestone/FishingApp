"""
Generate a self-contained HTML fishing forecast report with:
- Tide charts (SVG area charts per day)
- Wind compass arrows + speed
- Wave height bars
- Best/worst time windows (timeline)
- Separate inshore vs offshore sections
- Location recommendations based on water temp + wind
Opens in browser, includes print/PDF export.
"""

import html as html_mod
import logging
import math
import webbrowser
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import zoneinfo
    CENTRAL = zoneinfo.ZoneInfo("America/Chicago")
except Exception:
    CENTRAL = timezone(timedelta(hours=-5))

try:
    from fishing_forecast.config import DEFAULT_AREA
    from fishing_forecast.scorer import generate_forecast
except ImportError:
    from config import DEFAULT_AREA
    from scorer import generate_forecast

logger = logging.getLogger(__name__)


# ── Format helpers ───────────────────────────────────────────────────────────

def _fmt12(time_24: str) -> str:
    """Convert 'HH:MM' 24h to '12:30 PM' 12h format."""
    try:
        h, m = int(time_24.split(":")[0]), time_24.split(":")[1]
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m} {suffix}"
    except Exception:
        return time_24


def _fmtdate(d) -> str:
    """Format a date object as M/DD."""
    return f"{d.month}/{d.day:02d}"


# ── Color helpers ────────────────────────────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 8: return "#22c55e"
    if score >= 6: return "#eab308"
    if score >= 4: return "#f97316"
    return "#ef4444"


def _quality_color(quality: str) -> str:
    return {"prime": "#22c55e", "good": "#3b82f6", "fair": "#eab308", "poor": "#ef4444"}.get(quality, "#94a3b8")


def _wave_color(height_ft: float) -> str:
    if height_ft <= 2: return "#22c55e"
    if height_ft <= 4: return "#eab308"
    if height_ft <= 6: return "#f97316"
    return "#ef4444"


# ── SVG Generators ───────────────────────────────────────────────────────────

def _gauge_svg(score: int, label: str, size: int = 120) -> str:
    color = _score_color(score)
    pct = score / 10
    arc_total = 270
    arc_deg = pct * arc_total
    r = size // 2 - 12
    cx = cy = size // 2

    def p2c(angle_deg):
        a = math.radians(angle_deg - 90)
        return cx + r * math.cos(a), cy + r * math.sin(a)

    sa = 135
    x1, y1 = p2c(sa)
    x2, y2 = p2c(sa + arc_deg)
    bx2, by2 = p2c(sa + arc_total)
    large = 1 if arc_deg > 180 else 0

    return f"""<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
      <path d="M {x1:.1f} {y1:.1f} A {r} {r} 0 1 1 {bx2:.1f} {by2:.1f}"
            class="svg-track" fill="none" stroke="#e5e7eb" stroke-width="10" stroke-linecap="round"/>
      <path d="M {x1:.1f} {y1:.1f} A {r} {r} 0 {large} 1 {x2:.1f} {y2:.1f}"
            fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round"/>
      <text x="{cx}" y="{cy-2}" text-anchor="middle" font-size="28" font-weight="bold" fill="{color}">{score}</text>
      <text x="{cx}" y="{cy+16}" text-anchor="middle" font-size="11" fill="#6b7280" class="svg-muted">/10</text>
      <text x="{cx}" y="{cy+38}" text-anchor="middle" font-size="11" font-weight="600" fill="#374151" class="svg-text">{label}</text>
    </svg>"""


def _tide_chart_svg(hourly_points, high_times, low_times, width=480, height=120, is_today=False, current_hour=None) -> str:
    """SVG area chart of hourly tide levels."""
    if not hourly_points:
        return '<div class="no-data">No tide data available</div>'

    pad_l, pad_r, pad_t, pad_b = 36, 12, 8, 24
    cw = width - pad_l - pad_r
    ch = height - pad_t - pad_b

    heights = [p.height_ft for p in hourly_points]
    min_h = min(heights) - 0.1
    max_h = max(heights) + 0.1
    h_range = max_h - min_h if max_h != min_h else 1

    def tx(i):
        return pad_l + (i / max(len(hourly_points) - 1, 1)) * cw

    def ty(v):
        return pad_t + ch - ((v - min_h) / h_range) * ch

    # Build polyline + fill
    pts = " ".join(f"{tx(i):.1f},{ty(p.height_ft):.1f}" for i, p in enumerate(hourly_points))
    fill_pts = f"{tx(0):.1f},{pad_t + ch} " + pts + f" {tx(len(hourly_points)-1):.1f},{pad_t + ch}"

    # Time labels at 6-hour marks
    time_labels = ""
    for i, p in enumerate(hourly_points):
        hr = int(p.time.split(":")[0])
        if hr % 6 == 0:
            label = "12 AM"
            if hr == 6: label = "6 AM"
            elif hr == 12: label = "12 PM"
            elif hr == 18: label = "6 PM"
            time_labels += f'<text x="{tx(i):.1f}" y="{height-2}" text-anchor="middle" font-size="9" fill="#94a3b8">{label}</text>'

    # Hi/Lo markers — show time labels
    markers = ""
    for i, p in enumerate(hourly_points):
        if p.time in high_times:
            hr = int(p.time.split(":")[0])
            am_pm = "AM" if hr < 12 else "PM"
            hr12 = hr % 12 or 12
            time_label = f"{hr12}{am_pm}"
            markers += f"""<circle cx="{tx(i):.1f}" cy="{ty(p.height_ft):.1f}" r="4" fill="#ef4444" stroke="white" stroke-width="1.5"/>
            <text x="{tx(i):.1f}" y="{ty(p.height_ft) - 8:.1f}" text-anchor="middle" font-size="9" font-weight="600" fill="#ef4444">H {p.height_ft:.1f}' @ {time_label}</text>"""
        if p.time in low_times:
            hr = int(p.time.split(":")[0])
            am_pm = "AM" if hr < 12 else "PM"
            hr12 = hr % 12 or 12
            time_label = f"{hr12}{am_pm}"
            markers += f"""<circle cx="{tx(i):.1f}" cy="{ty(p.height_ft):.1f}" r="4" fill="#3b82f6" stroke="white" stroke-width="1.5"/>
            <text x="{tx(i):.1f}" y="{ty(p.height_ft) + 14:.1f}" text-anchor="middle" font-size="9" font-weight="600" fill="#3b82f6">L {p.height_ft:.1f}' @ {time_label}</text>"""

    # Current time marker (today only)
    now_marker = ""
    if is_today and current_hour is not None and len(hourly_points) > 1:
        # Fractional index for current hour
        frac_idx = current_hour / 24.0 * (len(hourly_points) - 1)
        idx_lo = int(frac_idx)
        idx_hi = min(idx_lo + 1, len(hourly_points) - 1)
        frac = frac_idx - idx_lo
        interp_h = heights[idx_lo] + frac * (heights[idx_hi] - heights[idx_lo])
        nx = tx(frac_idx)
        ny = ty(interp_h)
        # Vertical dashed line + dot + "Now" label
        now_marker = f"""<line x1="{nx:.1f}" y1="{pad_t}" x2="{nx:.1f}" y2="{pad_t + ch}" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="4,3" opacity="0.7"/>
        <circle cx="{nx:.1f}" cy="{ny:.1f}" r="5" fill="#f59e0b" stroke="white" stroke-width="2"/>
        <text x="{nx:.1f}" y="{pad_t - 1:.1f}" text-anchor="middle" font-size="9" font-weight="700" fill="#f59e0b">Now</text>"""

    # Y-axis labels
    y_labels = ""
    for v in [min_h, (min_h + max_h) / 2, max_h]:
        y_labels += f'<text x="{pad_l-4}" y="{ty(v)+3:.1f}" text-anchor="end" font-size="9" fill="#94a3b8">{v:.1f}</text>'

    return f"""<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">
      <defs><linearGradient id="tideGrad" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="#0ea5e9" stop-opacity="0.3"/>
        <stop offset="100%" stop-color="#0ea5e9" stop-opacity="0.05"/>
      </linearGradient></defs>
      <polygon points="{fill_pts}" fill="url(#tideGrad)"/>
      <polyline points="{pts}" fill="none" stroke="#0ea5e9" stroke-width="2.5" stroke-linejoin="round"/>
      {markers}
      {now_marker}
      {time_labels}
      {y_labels}
    </svg>"""


def _wind_compass_svg(direction: str, speed: float, size: int = 80) -> str:
    """SVG compass with arrow showing wind direction and speed."""
    dirs = {
        "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
        "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
        "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
        "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
    }
    deg = dirs.get(direction, 0)
    cx = cy = size // 2
    r = size // 2 - 6

    if speed <= 10: color = "#22c55e"
    elif speed <= 15: color = "#eab308"
    elif speed <= 20: color = "#f97316"
    else: color = "#ef4444"

    labels = ""
    for lbl, angle in [("N", 0), ("E", 90), ("S", 180), ("W", 270)]:
        a = math.radians(angle - 90)
        lx = cx + (r + 1) * math.cos(a)
        ly = cy + (r + 1) * math.sin(a)
        labels += f'<text x="{lx:.0f}" y="{ly + 3:.0f}" text-anchor="middle" font-size="8" fill="#94a3b8" font-weight="600">{lbl}</text>'

    return f"""<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
      <circle cx="{cx}" cy="{cy}" r="{r-8}" class="svg-track" fill="none" stroke="#e5e7eb" stroke-width="1.5"/>
      {labels}
      <g transform="rotate({deg} {cx} {cy})">
        <line x1="{cx}" y1="{cy+12}" x2="{cx}" y2="{cy-r+14}" stroke="{color}" stroke-width="3" stroke-linecap="round"/>
        <polygon points="{cx},{cy-r+10} {cx-5},{cy-r+20} {cx+5},{cy-r+20}" fill="{color}"/>
      </g>
      <circle cx="{cx}" cy="{cy}" r="10" class="svg-center" fill="white" stroke="{color}" stroke-width="2"/>
      <text x="{cx}" y="{cy+4}" text-anchor="middle" font-size="9" font-weight="bold" fill="{color}">{speed:.0f}</text>
    </svg>"""


def _wave_bar_svg(height_ft: float, max_ft: float = 8.0, width: int = 200, bar_h: int = 32) -> str:
    """Horizontal bar showing wave height with scale."""
    color = _wave_color(height_ft)
    pct = min(height_ft / max_ft, 1.0)
    bar_w = pct * (width - 60)

    markers = ""
    for thresh, label in [(2, "2'"), (4, "4'"), (6, "6'")]:
        x = (thresh / max_ft) * (width - 60) + 30
        markers += f"""<line x1="{x:.0f}" y1="2" x2="{x:.0f}" y2="{bar_h-2}" class="svg-track" stroke="#e5e7eb" stroke-width="1" stroke-dasharray="2"/>
        <text x="{x:.0f}" y="{bar_h+10}" text-anchor="middle" font-size="8" fill="#94a3b8">{label}</text>"""

    return f"""<svg width="{width}" height="{bar_h + 14}" viewBox="0 0 {width} {bar_h + 14}">
      <rect x="30" y="4" width="{width-60}" height="{bar_h-8}" rx="4" class="svg-bg" fill="#f1f5f9"/>
      {markers}
      <rect x="30" y="4" width="{max(bar_w, 2):.0f}" height="{bar_h-8}" rx="4" fill="{color}" opacity="0.85"/>
      <text x="2" y="{bar_h//2 + 2}" font-size="12" font-weight="bold" fill="{color}">{height_ft:.1f}'</text>
    </svg>"""


def _timeline_svg(time_windows, width: int = 480, height: int = 50) -> str:
    """Timeline bar showing fishing quality windows across the day."""
    if not time_windows:
        return ""

    block_w = (width - 20) / len(time_windows)
    blocks = ""
    for i, tw in enumerate(time_windows):
        x = 10 + i * block_w
        color = _quality_color(tw.quality)
        blocks += f"""<rect x="{x:.0f}" y="4" width="{block_w - 4:.0f}" height="20" rx="4" fill="{color}" opacity="0.2"/>
        <rect x="{x:.0f}" y="4" width="{block_w - 4:.0f}" height="20" rx="4" fill="none" stroke="{color}" stroke-width="1.5"/>
        <text x="{x + (block_w-4)/2:.0f}" y="18" text-anchor="middle" font-size="9" font-weight="600" fill="{color}">{tw.quality.upper()}</text>
        <text x="{x + (block_w-4)/2:.0f}" y="38" text-anchor="middle" font-size="8" class="svg-time" fill="#64748b">{tw.label.split('–')[0].strip()}</text>"""

    last_end = time_windows[-1].label.split("–")[-1].strip() if time_windows else ""
    blocks += f'<text x="{width - 10}" y="38" text-anchor="end" font-size="8" class="svg-time" fill="#64748b">{last_end}</text>'

    return f"""<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">
      {blocks}
    </svg>"""


def _location_badge(location: str) -> str:
    icons = {
        "Back Lakes": "🏞️", "ICW": "🛤️", "Bay": "🌊", "Flats": "🏖️",
        "Reefs": "🪸", "Passes": "⛵", "Jetties": "🪨", "Deep": "🎯",
        "Channel": "🎯", "Protected": "🛡️", "Shoreline": "🏖️",
    }
    icon = "🗺️"
    for key, emoji in icons.items():
        if key.lower() in location.lower():
            icon = emoji
            break
    return f'{icon} {location}'


# ── HTML Generator ───────────────────────────────────────────────────────────

def generate_html_string(forecast) -> str:
    """Build the complete HTML string from a ForecastResult. No file I/O."""
    days = forecast.days

    if not days:
        return ""

    today = days[0]
    best_inshore = max(days, key=lambda d: d.inshore_score)
    best_offshore = max(days, key=lambda d: d.offshore_score)

    # ── Build share text (baked into HTML for Web Share API) ─────────────────
    off_go = "GO" if today.offshore_score >= 6 else "MARGINAL" if today.offshore_score >= 4 else "NO-GO"
    share_lines = [
        f"🎣 Fishing Forecast — {forecast.area}",
        f"{_fmtdate(days[0].date)} – {_fmtdate(days[-1].date)}",
        "",
        f"TODAY ({today.date.strftime('%a')} {_fmtdate(today.date)}):",
        f"  Inshore {today.inshore_score}/10 · Offshore {today.offshore_score}/10 ({off_go})",
        f"  🐟 {today.best_species}",
        f"  📍 {today.location_rec}",
        f"  ⏰ Best: {today.best_window}",
        f"  💨 {today.conditions.wind.speed_mph:.0f}mph {today.conditions.wind.direction} · 🌊 {today.conditions.buoy.wave_height_ft:.1f}ft · 🌡️ {today.conditions.buoy.water_temp_f:.0f}°F",
        "",
    ]
    for d in days[1:]:
        off_tag = "✅" if d.offshore_score >= 6 else "⚠️" if d.offshore_score >= 4 else "❌"
        share_lines.append(
            f"{d.date.strftime('%a')} {_fmtdate(d.date)}: IN {d.inshore_score} · OFF {d.offshore_score}{off_tag} · {d.conditions.wind.speed_mph:.0f}mph · {d.conditions.buoy.wave_height_ft:.1f}ft"
        )
    share_lines += [
        "",
        f"★ Best inshore: {best_inshore.date.strftime('%a')} {_fmtdate(best_inshore.date)} ({best_inshore.inshore_score}/10)",
        f"★ Best offshore: {best_offshore.date.strftime('%a')} {_fmtdate(best_offshore.date)} ({best_offshore.offshore_score}/10)",
    ]
    _raw = "\n".join(share_lines)
    # HTML-escape for safe embedding in a data attribute
    share_text_escaped = html_mod.escape(_raw, quote=True)

    # ── Build per-day detail sections ────────────────────────────────────────
    day_sections = ""
    for d in days:
        day_name = f"{d.date.strftime('%A')}, {_fmtdate(d.date)}"
        is_today = d.date == today.date

        badges = ""
        if is_today:
            badges += '<span class="badge badge-today">TODAY</span>'
        if not d.conditions.has_weather:
            badges += ' <span class="badge badge-extended">EXTENDED</span>'
        if d.date == best_inshore.date:
            badges += ' <span class="badge badge-inshore">★ Best Inshore</span>'
        if d.date == best_offshore.date:
            badges += ' <span class="badge badge-offshore">★ Best Offshore</span>'

        warnings_html = ""
        if d.warnings:
            warnings_html = '<div class="alert-box">' + ''.join(f'<div class="alert-item">⚠️ {w}</div>' for w in d.warnings) + '</div>'

        gaps_html = ""
        if d.data_gaps:
            gaps_html = f'<div class="data-gaps">📡 Data gaps: {", ".join(d.data_gaps)}</div>'

        off_status = "GO" if d.offshore_score >= 6 else "MARGINAL" if d.offshore_score >= 4 else "NO-GO"
        off_color = _score_color(d.offshore_score)

        tw_tooltips = ""
        for tw in d.time_windows:
            tw_tooltips += f'<div class="tw-tip"><span class="tw-dot" style="background:{_quality_color(tw.quality)}"></span><strong>{tw.label}</strong>: {tw.reason}</div>'

        day_sections += f"""
    <div class="day-section {'day-today' if is_today else ''}">
      <div class="day-header" data-day="day-{d.date.isoformat()}">
        <div>
          <h2>{day_name} {badges}</h2>
          <span class="day-factor">{d.key_factor}</span>
          <div class="print-summary">🐟 {d.best_species} &middot; 📍 {d.location_rec} &middot; ⏰ {d.best_window} &middot; 💨 {d.conditions.wind.speed_mph:.0f}mph {d.conditions.wind.direction} &middot; 🌊 {d.conditions.buoy.wave_height_ft:.1f}ft</div>
        </div>
        <div class="day-scores-mini">
          <span class="score-pill" style="background:{_score_color(d.inshore_score)}">IN {d.inshore_score}</span>
          <span class="score-pill" style="background:{_score_color(d.nearshore_score)}">NR {d.nearshore_score}</span>
          <span class="score-pill" style="background:{off_color}">OFF {d.offshore_score}</span>
          <span class="chevron" id="chev-{d.date.isoformat()}">▼</span>
        </div>
      </div>

      <div class="day-body" id="day-{d.date.isoformat()}" style="display:{'block' if is_today else 'none'}">
        {warnings_html}

        <div class="section-label">🕐 Fishing Windows</div>
        <div class="timeline-container">
          {_timeline_svg(d.time_windows)}
          <div class="tw-details">{tw_tooltips}</div>
          <div class="time-summary">
            <span class="ts-best">✅ Best: {d.best_window}</span>
            <span class="ts-worst">❌ Avoid: {d.worst_window}</span>
          </div>
        </div>

        <div class="two-col">
          <div class="col-card inshore-card">
            <div class="col-header">
              <h3>🏖️ Inshore</h3>
              {_gauge_svg(d.inshore_score, "Score", 90)}
            </div>
            <div class="rec-box">
              <div class="rec-label">📍 Where to Fish</div>
              <div class="rec-location">{_location_badge(d.location_rec)}</div>
              <div class="rec-reason">{d.location_reason}</div>
            </div>
            <div class="rec-box">
              <div class="rec-label">🐟 Target Species</div>
              <div class="rec-species">{d.best_species}</div>
            </div>
            <div class="detail-row-data">
              <div class="datum"><span class="datum-label">Water Temp</span><span class="datum-value">{d.conditions.buoy.water_temp_f:.1f}°F</span></div>
              <div class="datum"><span class="datum-label">Pressure</span><span class="datum-value">{d.conditions.buoy.pressure_mb:.1f} mb ({d.conditions.pressure_trend})</span></div>
              <div class="datum"><span class="datum-label">Cloud / Rain</span><span class="datum-value">{d.conditions.cloud_cover_pct}% / {d.conditions.rain_chance_pct}%</span></div>
            </div>
          </div>

          <div class="col-card offshore-card">
            <div class="col-header">
              <h3>🚤 Offshore</h3>
              {_gauge_svg(d.offshore_score, off_status, 90)}
            </div>
            <div class="wave-section">
              <div class="rec-label">🌊 Wave Height</div>
              {_wave_bar_svg(d.conditions.buoy.wave_height_ft)}
              <div class="wave-detail">{d.conditions.buoy.wave_height_ft:.1f} ft @ {d.conditions.buoy.wave_period_sec:.0f}s period</div>
            </div>
            <div class="detail-row-data">
              <div class="datum"><span class="datum-label">Seas</span><span class="datum-value">{'Calm — go fish!' if d.conditions.buoy.wave_height_ft <= 2 else 'Moderate — experienced only' if d.conditions.buoy.wave_height_ft <= 4 else 'Rough — stay inshore' if d.conditions.buoy.wave_height_ft <= 6 else 'Dangerous — do not go'}</span></div>
              <div class="datum"><span class="datum-label">Water Temp</span><span class="datum-value">{d.conditions.buoy.water_temp_f:.1f}°F</span></div>
            </div>
          </div>
        </div>

        <div class="two-col">
          <div class="col-card">
            <div class="wind-row">
              <div>
                <div class="section-label" style="margin:0 0 4px 0">💨 Wind</div>
                {_wind_compass_svg(d.conditions.wind.direction, d.conditions.wind.speed_mph)}
              </div>
              <div class="wind-details">
                <div class="wind-speed">{d.conditions.wind.speed_mph:.0f} <span class="wind-unit">mph</span></div>
                <div class="wind-dir">from {d.conditions.wind.direction or '—'}</div>
                <div class="wind-assessment">{'🟢 Calm — great for all' if d.conditions.wind.speed_mph <= 10 else '🟡 Breezy — fishable inshore' if d.conditions.wind.speed_mph <= 15 else '🟠 Windy — protected water only' if d.conditions.wind.speed_mph <= 20 else '🔴 Strong — unfishable'}</div>
              </div>
            </div>
          </div>

          <div class="col-card">
            <div class="section-label" style="margin:0 0 4px 0">🌊 Tides</div>
            {_tide_chart_svg(d.conditions.tide.hourly, d.conditions.tide.high_times, d.conditions.tide.low_times, is_today=is_today, current_hour=datetime.now(tz=CENTRAL).hour + datetime.now(tz=CENTRAL).minute / 60.0 if is_today else None)}
            <div class="tide-summary">
              Range: {d.conditions.tide.range_ft:.2f} ft &middot;
              Highs: {', '.join(_fmt12(t) for t in d.conditions.tide.high_times) or '—'} &middot;
              Lows: {', '.join(_fmt12(t) for t in d.conditions.tide.low_times) or '—'}
            </div>
          </div>
        </div>

        {gaps_html}
      </div>
    </div>"""

    # ── Week comparison table ────────────────────────────────────────────────
    week_rows = ""
    for d in days:
        off_label = "GO" if d.offshore_score >= 6 else "MARG" if d.offshore_score >= 4 else "NO"
        week_rows += f"""<tr>
          <td class="day-name">{d.date.strftime('%a')} {_fmtdate(d.date)}</td>
          <td><span class="score-pill" style="background:{_score_color(d.inshore_score)}">{d.inshore_score}</span></td>
          <td><span class="score-pill" style="background:{_score_color(d.nearshore_score)}">{d.nearshore_score}</span></td>
          <td><span class="score-pill" style="background:{_score_color(d.offshore_score)}">{d.offshore_score}<small> {off_label}</small></span></td>
          <td class="td-wind">{_wind_compass_svg(d.conditions.wind.direction, d.conditions.wind.speed_mph, 44)}</td>
          <td class="td-wave">{_wave_bar_svg(d.conditions.buoy.wave_height_ft, width=120, bar_h=24)}</td>
          <td>{d.best_species}</td>
          <td class="td-loc">{d.location_rec}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en" class="">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes">
<title>Fishing Forecast — {forecast.area}</title>
<script>
  // Auto-detect system dark mode on load, before paint
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {{
    document.documentElement.classList.add('dark');
  }}
</script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#f0f4f8; color:#1e293b; line-height:1.5; }}
  .container {{ max-width:1200px; margin:0 auto; padding:20px; }}
  .header {{ background:linear-gradient(135deg,#0c4a6e,#0284c7); color:white; padding:28px 32px; border-radius:16px; margin-bottom:20px; }}
  .header h1 {{ font-size:26px; }}
  .header .area {{ font-size:15px; opacity:0.9; }}
  .header .subtitle {{ font-size:12px; opacity:0.7; margin-top:2px; }}
  .top-bar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; flex-wrap:wrap; gap:8px; }}
  .btn {{ background:#0369a1; color:white; border:none; padding:5px 12px; border-radius:6px; cursor:pointer; font-size:12px; font-weight:500; }}
  .btn:hover {{ background:#0c4a6e; }}
  .btn-outline {{ background:transparent; border:2px solid #0369a1; color:#0369a1; }}
  .btn-outline:hover {{ background:#0369a1; color:white; }}
  .gauge-row {{ display:flex; justify-content:center; gap:24px; margin-bottom:20px; flex-wrap:wrap; }}
  .gauge-item {{ text-align:center; background:white; border-radius:14px; padding:16px 24px; box-shadow:0 1px 3px rgba(0,0,0,0.06); }}
  .gauge-item h3 {{ font-size:13px; color:#64748b; margin-top:2px; }}
  .callout {{ background:white; border-left:4px solid #0369a1; padding:14px 18px; border-radius:0 12px 12px 0; margin-bottom:16px; box-shadow:0 1px 2px rgba(0,0,0,0.04); display:flex; gap:20px; flex-wrap:wrap; }}
  .callout-item {{ min-width:130px; }}
  .callout-item .label {{ font-size:11px; text-transform:uppercase; color:#64748b; letter-spacing:.5px; }}
  .callout-item .value {{ font-size:16px; font-weight:600; }}
  .best-days {{ display:flex; gap:14px; margin-bottom:20px; flex-wrap:wrap; }}
  .best-day-card {{ flex:1; min-width:220px; background:white; border-radius:12px; padding:16px; box-shadow:0 1px 2px rgba(0,0,0,0.06); border-top:3px solid; }}
  .best-day-card.inshore {{ border-color:#22c55e; }}
  .best-day-card.offshore {{ border-color:#3b82f6; }}
  .best-day-card h3 {{ font-size:13px; color:#64748b; }}
  .best-day-card .day {{ font-size:20px; font-weight:700; }}
  .best-day-card .meta {{ font-size:12px; color:#94a3b8; margin-top:2px; }}
  .week-table {{ width:100%; border-collapse:separate; border-spacing:0; background:white; border-radius:12px; overflow:hidden; box-shadow:0 1px 3px rgba(0,0,0,0.06); margin-bottom:20px; }}
  .week-table th {{ background:#f1f5f9; padding:10px; text-align:left; font-size:11px; text-transform:uppercase; color:#64748b; letter-spacing:.5px; }}
  .week-table td {{ padding:8px 10px; border-top:1px solid #f1f5f9; font-size:13px; vertical-align:middle; }}
  .td-wind {{ width:50px; text-align:center; }}
  .td-wave {{ width:130px; }}
  .td-loc {{ font-size:11px; max-width:150px; color:#475569; }}
  .score-pill {{ display:inline-block; min-width:36px; padding:2px 6px; text-align:center; border-radius:6px; color:white; font-weight:700; font-size:12px; white-space:nowrap; }}
  .score-pill small {{ font-weight:400; font-size:9px; opacity:0.9; }}
  .badge {{ display:inline-block; font-size:10px; padding:2px 8px; border-radius:10px; font-weight:600; margin-left:4px; vertical-align:middle; }}
  .badge-inshore {{ background:#dcfce7; color:#166534; }}
  .badge-offshore {{ background:#dbeafe; color:#1e40af; }}
  .badge-today {{ background:#fef3c7; color:#92400e; }}
  .badge-extended {{ background:#e0e7ff; color:#3730a3; }}
  .day-section {{ background:white; border-radius:14px; margin-bottom:14px; box-shadow:0 1px 3px rgba(0,0,0,0.06); overflow:hidden; }}
  .day-today {{ border:2px solid #0ea5e9; }}
  .day-header {{ display:flex; justify-content:space-between; align-items:center; padding:14px 20px; cursor:pointer; transition:background .15s; }}
  .day-header:hover {{ background:#f8fafc; }}
  .day-header h2 {{ font-size:17px; }}
  .day-factor {{ font-size:12px; color:#64748b; }}
  .day-scores-mini {{ display:flex; gap:6px; align-items:center; }}
  .chevron {{ font-size:12px; color:#94a3b8; margin-left:8px; transition:transform .2s; }}
  .chevron.open {{ transform:rotate(180deg); }}
  .day-body {{ padding:0 20px 20px; }}
  .section-label {{ font-size:12px; font-weight:600; text-transform:uppercase; color:#64748b; letter-spacing:.5px; margin:16px 0 6px; }}
  .timeline-container {{ background:#f8fafc; border-radius:10px; padding:12px 16px; margin-bottom:14px; }}
  .tw-details {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
  .tw-tip {{ font-size:11px; color:#475569; flex:1 1 180px; }}
  .tw-dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:4px; vertical-align:middle; }}
  .time-summary {{ display:flex; gap:16px; margin-top:8px; font-size:12px; }}
  .ts-best {{ color:#16a34a; font-weight:600; }}
  .ts-worst {{ color:#dc2626; font-weight:600; }}
  .two-col {{ display:flex; gap:14px; margin-bottom:14px; flex-wrap:wrap; }}
  .col-card {{ flex:1; min-width:280px; background:#f8fafc; border-radius:10px; padding:14px 16px; }}
  .inshore-card {{ border-left:3px solid #22c55e; }}
  .offshore-card {{ border-left:3px solid #3b82f6; }}
  .col-header {{ display:flex; justify-content:space-between; align-items:center; }}
  .col-header h3 {{ font-size:15px; }}
  .rec-box {{ background:white; border-radius:8px; padding:10px 12px; margin:8px 0; border:1px solid #e2e8f0; }}
  .rec-label {{ font-size:11px; text-transform:uppercase; color:#64748b; letter-spacing:.5px; margin-bottom:2px; }}
  .rec-location {{ font-size:16px; font-weight:700; color:#0c4a6e; }}
  .rec-reason {{ font-size:12px; color:#475569; margin-top:2px; line-height:1.4; }}
  .rec-species {{ font-size:16px; font-weight:700; color:#0c4a6e; }}
  .wave-section {{ margin:8px 0; }}
  .wave-detail {{ font-size:12px; color:#64748b; margin-top:2px; }}
  .wind-row {{ display:flex; align-items:center; gap:16px; }}
  .wind-details {{ flex:1; }}
  .wind-speed {{ font-size:28px; font-weight:700; color:#0c4a6e; }}
  .wind-unit {{ font-size:14px; font-weight:400; color:#64748b; }}
  .wind-dir {{ font-size:13px; color:#64748b; }}
  .wind-assessment {{ font-size:12px; margin-top:4px; }}
  .tide-summary {{ font-size:11px; color:#64748b; margin-top:4px; }}
  .detail-row-data {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
  .datum {{ flex:1 1 140px; background:white; border-radius:6px; padding:6px 10px; border:1px solid #e2e8f0; }}
  .datum-label {{ display:block; font-size:10px; text-transform:uppercase; color:#94a3b8; letter-spacing:.3px; }}
  .datum-value {{ font-size:13px; font-weight:600; color:#334155; }}
  .alert-box {{ background:#fef2f2; border:1px solid #fecaca; border-radius:8px; padding:8px 12px; margin-bottom:10px; }}
  .alert-item {{ font-size:12px; color:#991b1b; }}
  .data-gaps {{ font-size:11px; color:#94a3b8; margin-top:8px; }}
  .no-data {{ font-size:12px; color:#94a3b8; text-align:center; padding:20px; }}
  .print-summary {{ display:none; }}
  .footer {{ text-align:center; font-size:11px; color:#94a3b8; margin-top:24px; padding-top:12px; border-top:1px solid #e2e8f0; }}

  /* ── Dark Mode ── */
  .dark body {{ background:#0f172a; color:#e2e8f0; }}
  .dark .header {{ background:linear-gradient(135deg,#0f172a,#1e3a5f); }}
  .dark .gauge-item,.dark .best-day-card,.dark .day-section,.dark .week-table,.dark .callout {{ background:#1e293b; box-shadow:0 1px 3px rgba(0,0,0,0.3); }}
  .dark .callout {{ border-left-color:#0ea5e9; }}
  .dark .callout-item .label,.dark .gauge-item h3,.dark .best-day-card h3,.dark .day-factor,.dark .chevron,.dark .section-label,.dark .rec-label,.dark .wave-detail,.dark .wind-unit,.dark .wind-dir,.dark .tide-summary,.dark .datum-label,.dark .data-gaps,.dark .no-data,.dark .footer {{ color:#94a3b8; }}
  .dark .callout-item .value,.dark .best-day-card .day,.dark .day-header h2,.dark .rec-location,.dark .rec-species,.dark .wind-speed,.dark .datum-value {{ color:#e2e8f0; }}
  .dark .best-day-card .meta,.dark .rec-reason,.dark .tw-tip,.dark .td-loc,.dark .wind-assessment {{ color:#94a3b8; }}
  .dark .week-table th {{ background:#1e293b; color:#94a3b8; }}
  .dark .week-table td {{ border-top-color:#334155; }}
  .dark .day-header:hover {{ background:#334155; }}
  .dark .col-card,.dark .timeline-container {{ background:#1e293b; }}
  .dark .rec-box,.dark .datum {{ background:#0f172a; border-color:#334155; }}
  .dark .alert-box {{ background:#450a0a; border-color:#7f1d1d; }}
  .dark .alert-item {{ color:#fca5a5; }}
  .dark .btn {{ background:#0ea5e9; color:#0f172a; font-weight:600; }}
  .dark .btn:hover {{ background:#38bdf8; color:#0f172a; }}
  .dark .btn-outline {{ background:rgba(56,189,248,0.15); border-color:#7dd3fc; color:#e0f2fe; font-weight:600; }}
  .dark .btn-outline:hover {{ background:#38bdf8; color:#0f172a; }}
  .dark .hint-text {{ color:#94a3b8; }}
  .dark .day-today {{ border-color:#0ea5e9; }}
  .dark .badge-inshore {{ background:#064e3b; color:#6ee7b7; }}
  .dark .badge-offshore {{ background:#1e3a5f; color:#93c5fd; }}
  .dark .badge-today {{ background:#78350f; color:#fcd34d; }}
  .dark .badge-extended {{ background:#312e81; color:#a5b4fc; }}
  .dark .footer {{ border-top-color:#334155; }}

  .dark .svg-muted {{ fill:#94a3b8; }}
  .dark .svg-text {{ fill:#e2e8f0; }}
  .dark .svg-track {{ stroke:#475569; }}
  .dark .svg-bg {{ fill:#334155; }}
  .dark .svg-center {{ fill:#1e293b; }}
  .dark .svg-time {{ fill:#94a3b8; }}

  /* ── Mobile ── */
  @media (max-width:640px) {{
    .container {{ padding:12px; }}
    .header {{ padding:20px; }}
    .header h1 {{ font-size:22px; }}
    .gauge-row {{ gap:12px; }}
    .gauge-item {{ padding:10px 16px; }}
    .week-table {{ display:block; overflow-x:auto; -webkit-overflow-scrolling:touch; }}
    .two-col {{ flex-direction:column; }}
    .col-card {{ min-width:unset; }}
    .day-header {{ flex-direction:column; align-items:flex-start; gap:8px; }}
    .day-scores-mini {{ width:100%; justify-content:flex-start; }}
    .callout {{ gap:12px; }}
    .callout-item {{ min-width:100px; }}
    .wind-speed {{ font-size:22px; }}
    .time-summary {{ flex-direction:column; gap:4px; }}
    .btn {{ padding:4px 10px; font-size:11px; border-radius:6px; }}
    .btn-outline {{ border-width:1.5px; }}
    .top-bar {{ gap:4px; }}
  }}

  @media print {{
    /* ── iPhone-sized minimal PDF: ~390px portrait ── */
    @page {{ size:90mm 190mm; margin:4mm; }}
    * {{ -webkit-print-color-adjust:exact !important; print-color-adjust:exact !important; color-adjust:exact !important; }}
    body {{ background:white; font-size:10px; color:#1e293b; }}
    .no-print,.top-bar,.gauge-row,.callout,.best-days,.week-table,.footer,.chevron {{ display:none !important; }}
    .container {{ padding:0; max-width:100%; }}
    .header {{ padding:10px 14px; margin-bottom:8px; border-radius:8px; }}
    .header h1 {{ font-size:16px; }}
    .header .area {{ font-size:11px; }}
    .header .subtitle {{ font-size:9px; }}

    .day-section {{ border-radius:8px; margin-bottom:6px; box-shadow:none; border:1px solid #e2e8f0; break-inside:avoid; page-break-inside:avoid; }}
    .day-today {{ border:1.5px solid #0ea5e9; }}
    .day-header {{ padding:8px 10px; }}
    .day-header h2 {{ font-size:12px; }}
    .day-factor {{ font-size:9px; }}
    .day-scores-mini {{ gap:4px; }}
    .score-pill {{ font-size:10px; padding:1px 5px; min-width:30px; }}
    .badge {{ font-size:8px; padding:1px 5px; }}

    /* Hide expanded body — show only header cards */
    .day-body {{ display:none !important; }}
    .print-summary {{ display:block; font-size:9px; color:#475569; margin-top:2px; line-height:1.4; }}
  }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🎣 Fishing Forecast</h1>
    <div class="area">{forecast.area}</div>
    <div class="subtitle">Generated {forecast.generated_at} &middot; {_fmtdate(days[0].date)} – {_fmtdate(days[-1].date)}/{days[-1].date.year}{' &middot; Extended search (no great days in 7-day window)' if len(days) > 7 else ''}</div>
  </div>

  <div class="top-bar no-print">
    <div>
      <button class="btn" id="shareBtn" data-share-text="{share_text_escaped}">📤 Share</button>
      <button class="btn btn-outline" id="pdfBtn" style="margin-left:4px">🖨️ Print</button>
      <button class="btn btn-outline" id="expandBtn" style="margin-left:4px">Expand All</button>
      <button class="btn btn-outline" id="collapseBtn" style="margin-left:4px">Collapse All</button>
      <button class="btn btn-outline" id="darkBtn" style="margin-left:4px">🌙 Dark</button>
    </div>
    <div class="hint-text" style="font-size:12px;color:#64748b">Click any day to expand</div>
  </div>

  <div class="gauge-row">
    <div class="gauge-item">{_gauge_svg(today.inshore_score, "Inshore")}<h3>Inshore</h3></div>
    <div class="gauge-item">{_gauge_svg(today.nearshore_score, "Nearshore")}<h3>Nearshore</h3></div>
    <div class="gauge-item">{_gauge_svg(today.offshore_score, "GO" if today.offshore_score >= 6 else "NO-GO")}<h3>Offshore</h3></div>
  </div>

  <div class="callout">
    <div class="callout-item"><div class="label">Target</div><div class="value">🐟 {today.best_species}</div></div>
    <div class="callout-item"><div class="label">Where</div><div class="value">{_location_badge(today.location_rec)}</div></div>
    <div class="callout-item"><div class="label">Best Window</div><div class="value">{today.best_window}</div></div>
    <div class="callout-item"><div class="label">Water</div><div class="value">{today.conditions.buoy.water_temp_f:.1f}°F</div></div>
    <div class="callout-item"><div class="label">Wind</div><div class="value">{today.conditions.wind.speed_mph:.0f} mph {today.conditions.wind.direction}</div></div>
    <div class="callout-item"><div class="label">Waves</div><div class="value">{today.conditions.buoy.wave_height_ft:.1f} ft</div></div>
  </div>

  <div class="best-days">
    <div class="best-day-card inshore">
      <h3>★ Best Inshore Day</h3>
      <div class="day">{best_inshore.date.strftime('%A')}, {_fmtdate(best_inshore.date)}</div>
      <div class="meta">{best_inshore.inshore_score}/10 &middot; {best_inshore.best_species} &middot; {best_inshore.location_rec}</div>
    </div>
    <div class="best-day-card offshore">
      <h3>{"★ Best Offshore Day" if best_offshore.offshore_score >= 5 else "⚠️ Offshore — Best Available"}</h3>
      <div class="day">{best_offshore.date.strftime('%A')}, {_fmtdate(best_offshore.date)}</div>
      <div class="meta">{best_offshore.offshore_score}/10 &middot; Waves {best_offshore.conditions.buoy.wave_height_ft:.1f} ft &middot; Wind {best_offshore.conditions.wind.speed_mph:.0f} mph {"— ✅ Fishable" if best_offshore.offshore_score >= 6 else "— ⚠️ Marginal" if best_offshore.offshore_score >= 4 else "— ❌ Rough"}</div>
    </div>
  </div>

  <table class="week-table">
    <thead><tr><th>Day</th><th>Inshore</th><th>Near</th><th>Offshore</th><th>Wind</th><th>Waves</th><th>Species</th><th>Where</th></tr></thead>
    <tbody>{week_rows}</tbody>
  </table>

  {day_sections}

  <div class="footer">Fishing Forecast v1.2.3 &middot; {forecast.area} &middot; NOAA / NDBC / NWS &middot; {forecast.generated_at}</div>
</div>

<script>
function toggleDay(id) {{
  const el = document.getElementById(id);
  const chev = document.getElementById('chev-' + id.replace('day-',''));
  if (el) {{
    const show = el.style.display === 'none';
    el.style.display = show ? 'block' : 'none';
    if (chev) chev.classList.toggle('open', show);
  }}
}}
function expandAll() {{
  document.querySelectorAll('.day-body').forEach(el => el.style.display = 'block');
  document.querySelectorAll('.chevron').forEach(c => c.classList.add('open'));
}}
function collapseAll() {{
  document.querySelectorAll('.day-body').forEach(el => el.style.display = 'none');
  document.querySelectorAll('.chevron').forEach(c => c.classList.remove('open'));
}}
function toggleDark() {{
  const html = document.documentElement;
  html.classList.toggle('dark');
  const btn = document.getElementById('darkBtn');
  btn.textContent = html.classList.contains('dark') ? '☀️ Light' : '🌙 Dark';
}}
// Wire up all event listeners (no inline onclick — CSP safe)
document.addEventListener('DOMContentLoaded', () => {{
  const darkBtn = document.getElementById('darkBtn');
  if (darkBtn && document.documentElement.classList.contains('dark')) darkBtn.textContent = '☀️ Light';

  // Toolbar buttons
  document.getElementById('shareBtn').addEventListener('click', shareForecast);
  document.getElementById('pdfBtn').addEventListener('click', async () => {{
    // On iOS/mobile WebView, window.print() is not supported — use share sheet which has Print
    if (/iPhone|iPad|iPod|Android/i.test(navigator.userAgent) && navigator.share) {{
      try {{
        await navigator.share({{ title: '🎣 Fishing Forecast', url: window.location.href }});
      }} catch(e) {{ if (e.name !== 'AbortError') console.error(e); }}
    }} else {{
      window.print();
    }}
  }});
  document.getElementById('expandBtn').addEventListener('click', expandAll);
  document.getElementById('collapseBtn').addEventListener('click', collapseAll);
  darkBtn.addEventListener('click', toggleDark);

  // Day-header accordion — event delegation
  document.addEventListener('click', (e) => {{
    const hdr = e.target.closest('.day-header[data-day]');
    if (hdr) toggleDay(hdr.getAttribute('data-day'));
  }});
}});
async function shareForecast() {{
  const text = document.getElementById('shareBtn').getAttribute('data-share-text');
  if (navigator.share) {{
    try {{
      await navigator.share({{ title: '🎣 Fishing Forecast', text: text }});
    }} catch(e) {{
      if (e.name !== 'AbortError') console.error(e);
    }}
  }} else {{
    try {{
      await navigator.clipboard.writeText(text);
      const b = document.getElementById('shareBtn');
      const orig = b.textContent;
      b.textContent = '✅ Copied!';
      setTimeout(() => b.textContent = orig, 2000);
    }} catch(e) {{
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      alert('Forecast copied to clipboard!');
    }}
  }}
}}
</script>
</body>
</html>"""

    return html


def generate_html(area_key: str = DEFAULT_AREA, output_path: str = "fishing_forecast.html") -> str:
    """Generate forecast then write HTML report to disk."""
    forecast = generate_forecast(area_key)
    html = generate_html_string(forecast)
    if not html:
        return ""

    out = Path(output_path)
    out.write_text(html, encoding="utf-8")
    logger.info("HTML report written to %s", out.resolve())
    return str(out.resolve())


def open_report(area_key: str = DEFAULT_AREA, output_path: str = "fishing_forecast.html") -> str:
    path = generate_html(area_key, output_path)
    webbrowser.open(f"file:///{path}")
    return path
