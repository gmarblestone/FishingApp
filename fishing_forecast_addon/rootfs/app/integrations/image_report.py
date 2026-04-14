"""
Generate a JPG fishing forecast summary card using Pillow.
Designed for sharing via text/social and printing.
"""

import logging
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    from PIL import Image, ImageDraw, ImageFont

try:
    from fishing_forecast.config import DEFAULT_AREA
    from fishing_forecast.scorer import generate_forecast
except ImportError:
    from config import DEFAULT_AREA
    from scorer import generate_forecast

logger = logging.getLogger(__name__)

# Card dimensions (iPhone-friendly aspect ratio)
CARD_W = 1080
CARD_H = 1920

# Colors
BG = "#0f172a"
HEADER_BG = "#0c4a6e"
CARD_BG = "#1e293b"
WHITE = "#f8fafc"
MUTED = "#94a3b8"
GREEN = "#22c55e"
YELLOW = "#eab308"
ORANGE = "#f97316"
RED = "#ef4444"
BLUE = "#0ea5e9"
LIGHT_BLUE = "#38bdf8"


def _score_color(score: int) -> str:
    if score >= 8: return GREEN
    if score >= 6: return YELLOW
    if score >= 4: return ORANGE
    return RED


def _fmtdate(d) -> str:
    return f"{d.month}/{d.day:02d}"


def _fmt12(time_24: str) -> str:
    try:
        h, m = int(time_24.split(":")[0]), time_24.split(":")[1]
        suffix = "AM" if h < 12 else "PM"
        h12 = h % 12 or 12
        return f"{h12}:{m} {suffix}"
    except Exception:
        return time_24


def _load_font(size: int):
    """Try to load a clean font, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _load_font_bold(size: int):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for fp in font_paths:
        try:
            return ImageFont.truetype(fp, size)
        except (OSError, IOError):
            continue
    return _load_font(size)


def generate_image_string(forecast) -> Image.Image:
    """Build a forecast summary card as a PIL Image."""
    days = forecast.days
    if not days:
        return None

    today = days[0]
    best_inshore = max(days, key=lambda d: d.inshore_score)
    best_offshore = max(days, key=lambda d: d.offshore_score)

    img = Image.new("RGB", (CARD_W, CARD_H), BG)
    draw = ImageDraw.Draw(img)

    # Fonts
    f_title = _load_font_bold(48)
    f_area = _load_font(30)
    f_section = _load_font_bold(28)
    f_big = _load_font_bold(64)
    f_med = _load_font_bold(32)
    f_body = _load_font(26)
    f_small = _load_font(22)
    f_tiny = _load_font(18)

    y = 0

    # ── Header ───────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, CARD_W, 160], fill=HEADER_BG)
    draw.text((40, 30), "Fishing Forecast", fill=WHITE, font=f_title)
    draw.text((40, 90), forecast.area, fill=MUTED, font=f_area)
    draw.text((40, 125), f"Generated {forecast.generated_at}", fill=MUTED, font=f_tiny)
    y = 180

    # ── Today's scores ───────────────────────────────────────────────────────
    draw.rounded_rectangle([30, y, CARD_W - 30, y + 200], radius=16, fill=CARD_BG)
    draw.text((60, y + 12), f"TODAY - {today.date.strftime('%A')}, {_fmtdate(today.date)}", fill=LIGHT_BLUE, font=f_section)

    # Score boxes
    scores = [
        ("Inshore", today.inshore_score),
        ("Near", today.nearshore_score),
        ("Offshore", today.offshore_score),
    ]
    box_w = 280
    for i, (label, score) in enumerate(scores):
        bx = 60 + i * (box_w + 30)
        by = y + 60
        draw.rounded_rectangle([bx, by, bx + box_w, by + 120], radius=12, fill=_score_color(score))
        draw.text((bx + 20, by + 10), str(score), fill="#0f172a", font=f_big)
        draw.text((bx + 100, by + 40), f"/10", fill="#0f172a", font=f_body)
        draw.text((bx + 20, by + 85), label, fill="#0f172a", font=f_small)
    y += 220

    # ── Today's details ──────────────────────────────────────────────────────
    draw.rounded_rectangle([30, y, CARD_W - 30, y + 260], radius=16, fill=CARD_BG)
    details = [
        ("Target", today.best_species),
        ("Where", today.location_rec),
        ("Best Window", today.best_window),
        ("Wind", f"{today.conditions.wind.speed_mph:.0f} mph {today.conditions.wind.direction}"),
        ("Waves", f"{today.conditions.buoy.wave_height_ft:.1f} ft"),
        ("Water", f"{today.conditions.buoy.water_temp_f:.1f}F"),
    ]
    dx = 60
    dy = y + 16
    for label, value in details:
        draw.text((dx, dy), label, fill=MUTED, font=f_tiny)
        draw.text((dx + 180, dy), value, fill=WHITE, font=f_small)
        dy += 38
    y += 280

    # ── Best days ────────────────────────────────────────────────────────────
    draw.rounded_rectangle([30, y, CARD_W // 2 - 10, y + 140], radius=16, fill=CARD_BG)
    draw.text((50, y + 12), "Best Inshore", fill=GREEN, font=f_small)
    draw.text((50, y + 45), f"{best_inshore.date.strftime('%A')}, {_fmtdate(best_inshore.date)}", fill=WHITE, font=f_med)
    draw.text((50, y + 90), f"{best_inshore.inshore_score}/10 - {best_inshore.best_species}", fill=MUTED, font=f_small)

    draw.rounded_rectangle([CARD_W // 2 + 10, y, CARD_W - 30, y + 140], radius=16, fill=CARD_BG)
    draw.text((CARD_W // 2 + 30, y + 12), "Best Offshore", fill=BLUE, font=f_small)
    draw.text((CARD_W // 2 + 30, y + 45), f"{best_offshore.date.strftime('%A')}, {_fmtdate(best_offshore.date)}", fill=WHITE, font=f_med)
    off_status = "Fishable" if best_offshore.offshore_score >= 6 else "Marginal" if best_offshore.offshore_score >= 4 else "Rough"
    draw.text((CARD_W // 2 + 30, y + 90), f"{best_offshore.offshore_score}/10 - {off_status}", fill=MUTED, font=f_small)
    y += 160

    # ── Week overview ────────────────────────────────────────────────────────
    draw.text((40, y + 10), "FORECAST", fill=MUTED, font=f_section)
    y += 50

    row_h = 70
    max_rows = min(len(days), 14)
    for idx, d in enumerate(days[:max_rows]):
        ry = y + idx * row_h
        # Alternate row bg
        if idx % 2 == 0:
            draw.rounded_rectangle([30, ry, CARD_W - 30, ry + row_h - 4], radius=10, fill=CARD_BG)

        # Date
        day_label = "TODAY" if idx == 0 else d.date.strftime("%a")
        draw.text((50, ry + 8), day_label, fill=WHITE if idx == 0 else MUTED, font=f_small)
        draw.text((50, ry + 35), _fmtdate(d.date), fill=MUTED, font=f_tiny)

        # Scores
        for j, (score, label) in enumerate([
            (d.inshore_score, "IN"),
            (d.nearshore_score, "NR"),
            (d.offshore_score, "OFF"),
        ]):
            sx = 230 + j * 170
            pill_w = 90
            draw.rounded_rectangle([sx, ry + 12, sx + pill_w, ry + row_h - 16], radius=8, fill=_score_color(score))
            draw.text((sx + 8, ry + 16), f"{label} {score}", fill="#0f172a", font=f_small)

        # Wind + waves
        draw.text((760, ry + 12), f"{d.conditions.wind.speed_mph:.0f}mph", fill=MUTED, font=f_small)
        draw.text((760, ry + 38), f"{d.conditions.buoy.wave_height_ft:.1f}ft", fill=MUTED, font=f_tiny)

        # Species
        species_short = d.best_species[:15] + "..." if len(d.best_species) > 15 else d.best_species
        draw.text((890, ry + 20), species_short, fill=MUTED, font=f_tiny)

    y += max_rows * row_h + 10

    # ── Tides for today ──────────────────────────────────────────────────────
    if today.conditions.tide.high_times or today.conditions.tide.low_times:
        tides_text = "Tides: "
        tides_text += "H " + ", ".join(_fmt12(t) for t in today.conditions.tide.high_times)
        tides_text += " | L " + ", ".join(_fmt12(t) for t in today.conditions.tide.low_times)
        draw.text((40, y), tides_text, fill=MUTED, font=f_small)
        y += 35

    # ── Footer ───────────────────────────────────────────────────────────────
    footer_y = CARD_H - 50
    draw.text((40, footer_y), f"Fishing Forecast v1.2.3 | NOAA / NDBC / NWS | {forecast.generated_at}", fill="#64748b", font=f_tiny)

    return img


def generate_image(forecast, output_path: str = "/config/www/fishing_forecast.jpg") -> str:
    """Generate forecast JPG and write to disk."""
    img = generate_image_string(forecast)
    if not img:
        logger.error("No image generated")
        return ""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, "JPEG", quality=90)
    logger.info("JPG written to %s", output_path)
    return output_path
