from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Optional


@dataclass
class TidePoint:
    time: str = ""  # HH:MM
    height_ft: float = 0.0


@dataclass
class TideData:
    high_times: list[str] = field(default_factory=list)
    low_times: list[str] = field(default_factory=list)
    range_ft: float = 0.0
    hourly: list[TidePoint] = field(default_factory=list)  # for chart


@dataclass
class WindData:
    speed_mph: float = 0.0
    gust_mph: float = 0.0
    direction: str = ""


@dataclass
class BuoyData:
    wave_height_ft: float = 0.0
    wave_period_sec: float = 0.0
    water_temp_f: float = 0.0
    pressure_mb: float = 0.0


@dataclass
class SolunarData:
    major1: str = ""
    major2: str = ""
    minor1: str = ""
    minor2: str = ""
    moon_phase: str = ""
    rating: int = 0  # 1-5


@dataclass
class DayConditions:
    date: date = field(default_factory=date.today)
    tide: TideData = field(default_factory=TideData)
    wind: WindData = field(default_factory=WindData)
    buoy: BuoyData = field(default_factory=BuoyData)
    solunar: SolunarData = field(default_factory=SolunarData)
    pressure_trend: str = ""  # rising, falling, stable
    cloud_cover_pct: int = 0
    rain_chance_pct: int = 0
    air_temp_high_f: float = 0.0
    air_temp_low_f: float = 0.0


@dataclass
class TimeWindow:
    label: str = ""  # e.g. "6:00 AM - 9:00 AM"
    quality: str = ""  # "prime", "good", "fair", "poor"
    reason: str = ""  # why this window is rated this way


@dataclass
class DayForecast:
    date: date = field(default_factory=date.today)
    inshore_score: int = 0
    nearshore_score: int = 0
    offshore_score: int = 0
    best_species: str = ""
    best_window: str = ""
    worst_window: str = ""
    key_factor: str = ""
    location_rec: str = ""  # back lakes, ICW, bay, jetties
    location_reason: str = ""
    time_windows: list[TimeWindow] = field(default_factory=list)
    conditions: DayConditions = field(default_factory=DayConditions)
    warnings: list[str] = field(default_factory=list)
    data_gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date.isoformat()
        d["conditions"]["date"] = self.conditions.date.isoformat()
        return d


@dataclass
class ForecastResult:
    area: str = ""
    generated_at: str = ""
    days: list[DayForecast] = field(default_factory=list)
    best_inshore_day: Optional[str] = None
    best_offshore_day: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "area": self.area,
            "generated_at": self.generated_at,
            "days": [d.to_dict() for d in self.days],
            "best_inshore_day": self.best_inshore_day,
            "best_offshore_day": self.best_offshore_day,
        }
