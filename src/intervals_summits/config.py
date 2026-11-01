"""Settings: environment variables, else a settings file.

The settings file that applies: SUMMITS_ENV_FILE, else ./.env, else ~/IntervalsSummits/.env, else the
bridge's ~/GarminBridge/.env – so next to the Garmin bridge nothing has to be set twice. Variables
already set in the environment always win.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

HOME_FOLDER = "IntervalsSummits"
BRIDGE_FOLDER = "GarminBridge"
OVERPASS = "https://overpass-api.de/api/interpreter"
# indoor and virtual types: no track worth asking for ("Other" may well have one: paragliding, ...)
INDOOR = frozenset({"VirtualRide", "VirtualRun", "VirtualRow", "VirtualSki", "Elliptical", "Workout", "WeightTraining",
                    "Yoga", "Pilates", "Crossfit", "StairStepper", "Rowing", "Swim", "HighIntensityIntervalTraining"})
ALL_FIELDS = ("Summits", "SummitCount", "HighestPoint", "HutsPasses")
DEFAULT_FIELDS = ("Summits", "SummitCount", "HighestPoint")


def read_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def env_file() -> Path | None:
    if os.environ.get("SUMMITS_ENV_FILE"):
        return Path(os.environ["SUMMITS_ENV_FILE"]).expanduser()
    for candidate in (Path(".env"), Path.home() / HOME_FOLDER / ".env", Path.home() / BRIDGE_FOLDER / ".env"):
        if candidate.is_file():
            return candidate
    return None


def default_data_dir() -> Path:
    """Next to a bridge set up on this computer: ~/GarminBridge/summits; else ~/IntervalsSummits."""
    bridge = Path.home() / BRIDGE_FOLDER
    return bridge / "summits" if bridge.is_dir() else Path.home() / HOME_FOLDER


def _list(value: str | None) -> tuple[str, ...]:
    return tuple(v.strip() for v in (value or "").split(",") if v.strip())


def _bool(value: str | None, default: bool) -> bool:
    return default if value in (None, "") else value.strip().lower() in ("1", "true", "yes", "on")


def _metres(env: dict[str, str], key: str, default: float, low: float, high: float) -> float:
    value = env.get(key)
    if value in (None, ""):
        return default
    try:
        number = float(value)
    except ValueError:
        raise SystemExit(f"{key}: a number of metres, not {value!r}") from None
    if not low <= number <= high:
        raise SystemExit(f"{key}: {low:g} to {high:g} m")
    return number


@dataclass
class Settings:
    api_key: str
    athlete_id: str = "0"
    data_dir: Path = field(default_factory=default_data_dir)
    language: str = "en"                 # field names and the page: en or de
    name_language: str = ""              # OSM name:<xx> when there is one; "" = the local name
    types: tuple[str, ...] = ()          # only these activity types; () = every outdoor type
    fields: tuple[str, ...] = DEFAULT_FIELDS
    overpass_url: str = OVERPASS
    lookback_days: int = 3
    catchup_days: int = 14
    interval_minutes: int = 15
    pause: float = 0.6                   # seconds between Intervals requests (the key is shared with the bridge)
    keep_tracks: bool = True
    description: bool = False           # the line "⛰️ Summits: …" in the description (searchable)
    peak_radius: float = 100.0
    peak_below: float = 80.0
    hut_radius: float = 60.0
    pass_radius: float = 60.0
    page_title: str = ""

    @property
    def page_file(self) -> Path:
        return self.data_dir / "summits.html"

    @property
    def db_file(self) -> Path:
        return self.data_dir / "summits.sqlite"

    @property
    def tracks_dir(self) -> Path:
        return self.data_dir / "tracks"


def load(environ: dict[str, str] | None = None) -> Settings:
    env = dict(environ if environ is not None else os.environ)
    if environ is None and (path := env_file()):
        for key, value in read_env_file(path).items():
            env.setdefault(key, value)
    key = env.get("INTERVALS_API_KEY", "")
    if not key:
        raise SystemExit("INTERVALS_API_KEY is not set (environment or settings file)")
    fields = tuple(f for f in _list(env.get("SUMMITS_FIELDS")) or DEFAULT_FIELDS)
    unknown = [f for f in fields if f not in ALL_FIELDS]
    if unknown:
        raise SystemExit(f"SUMMITS_FIELDS: unknown {unknown}; possible: {', '.join(ALL_FIELDS)}")
    language = (env.get("SUMMITS_LANGUAGE") or "en").lower()[:2]
    return Settings(
        api_key=key,
        athlete_id=env.get("INTERVALS_ATHLETE_ID") or "0",
        data_dir=Path(env["SUMMITS_DATA_DIR"]).expanduser() if env.get("SUMMITS_DATA_DIR") else default_data_dir(),
        language=language if language in ("en", "de") else "en",
        name_language=(env.get("SUMMITS_NAME_LANGUAGE") or "").lower(),
        types=_list(env.get("SUMMITS_TYPES")),
        fields=fields,
        overpass_url=env.get("SUMMITS_OVERPASS_URL") or OVERPASS,
        lookback_days=max(1, min(30, int(env.get("SUMMITS_LOOKBACK_DAYS") or 3))),
        interval_minutes=max(5, int(env.get("SUMMITS_INTERVAL_MINUTES") or 15)),
        keep_tracks=_bool(env.get("SUMMITS_KEEP_TRACKS"), True),
        description=_bool(env.get("SUMMITS_DESCRIPTION"), False),
        # up to 200 m: a track point needs the neighbouring OpenStreetMap cell only within 0.004° of a border
        peak_radius=_metres(env, "SUMMITS_PEAK_RADIUS", 100.0, 10, 200),
        peak_below=_metres(env, "SUMMITS_PEAK_BELOW", 80.0, 0, 500),
        hut_radius=_metres(env, "SUMMITS_HUT_RADIUS", 60.0, 10, 200),
        pass_radius=_metres(env, "SUMMITS_PASS_RADIUS", 60.0, 10, 200),
        page_title=env.get("SUMMITS_PAGE_TITLE") or "",
    )
