import os
import re
import tomllib
from dataclasses import dataclass, field
from datetime import time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

LANGS = ("ru", "kk", "en")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
ID_RE = re.compile(r"^[a-z0-9_]{1,12}$")
ANY = "any"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Service:
    id: str
    names: dict[str, str]
    minutes: int
    price: int


@dataclass(frozen=True)
class Staff:
    id: str
    names: dict[str, str]
    services: tuple[str, ...]
    hours: dict[int, tuple[time, time]]
    lunch: tuple[time, time] | None = None


@dataclass(frozen=True)
class Rules:
    slot_minutes: int = 30
    min_lead_minutes: int = 60
    horizon_days: int = 14
    cancel_minutes: int = 120
    max_active: int = 2
    remind_hours: tuple[int, ...] = (24, 2)


@dataclass(frozen=True)
class Business:
    name: str
    phone: str
    tz: ZoneInfo
    currency: str
    address: dict[str, str]
    about: dict[str, str]
    services: dict[str, Service]
    staff: dict[str, Staff]
    rules: Rules = field(default_factory=Rules)

    def staff_for(self, service_id: str) -> list[Staff]:
        return [s for s in self.staff.values() if service_id in s.services]

    def service_name(self, service_id: str, lang: str) -> str:
        service = self.services.get(service_id)
        return pick(service.names, lang) if service else service_id

    def staff_name(self, staff_id: str, lang: str) -> str:
        staff = self.staff.get(staff_id)
        return pick(staff.names, lang) if staff else staff_id


@dataclass(frozen=True)
class Settings:
    token: str
    admins: frozenset[int]
    business_file: Path
    db_file: Path
    proxy: str | None


def pick(values: dict[str, str], lang: str) -> str:
    return values.get(lang) or values.get("ru") or next(iter(values.values()), "")


def localized(value: Any, what: str) -> dict[str, str]:
    if isinstance(value, str):
        return {lang: value for lang in LANGS}
    if isinstance(value, dict) and value and all(isinstance(v, str) for v in value.values()):
        return dict(value)
    raise ConfigError(f"{what}: expected a string or a table of translations")


def parse_time(text: str, what: str) -> time:
    try:
        hours, minutes = text.strip().split(":")
        return time(int(hours), int(minutes))
    except ValueError:
        raise ConfigError(f"{what}: bad time {text!r}, expected HH:MM") from None


def parse_range(text: str, what: str) -> tuple[time, time]:
    if not isinstance(text, str) or "-" not in text:
        raise ConfigError(f"{what}: expected HH:MM-HH:MM")
    start_text, end_text = text.split("-", 1)
    start, end = parse_time(start_text, what), parse_time(end_text, what)
    if start >= end:
        raise ConfigError(f"{what}: start must be before end")
    return start, end


def check_id(value: str, what: str) -> None:
    if not ID_RE.match(value) or value == ANY:
        raise ConfigError(f"{what}: id {value!r} must match [a-z0-9_]{{1,12}} and not be 'any'")


def parse_business(data: dict[str, Any]) -> Business:
    services: dict[str, Service] = {}
    for sid, raw in data.get("services", {}).items():
        check_id(sid, "services")
        minutes = raw.get("minutes")
        if not isinstance(minutes, int) or minutes <= 0:
            raise ConfigError(f"services.{sid}: minutes must be a positive integer")
        services[sid] = Service(sid, localized(raw.get("name"), f"services.{sid}.name"), minutes, int(raw.get("price", 0)))
    if not services:
        raise ConfigError("no services defined")

    staff: dict[str, Staff] = {}
    for mid, raw in data.get("staff", {}).items():
        check_id(mid, "staff")
        offered = tuple(raw.get("services") or services.keys())
        for sid in offered:
            if sid not in services:
                raise ConfigError(f"staff.{mid}: unknown service {sid!r}")
        hours: dict[int, tuple[time, time]] = {}
        for day, value in raw.get("hours", {}).items():
            if day not in WEEKDAYS:
                raise ConfigError(f"staff.{mid}.hours: unknown day {day!r}")
            hours[WEEKDAYS.index(day)] = parse_range(value, f"staff.{mid}.hours.{day}")
        if not hours:
            raise ConfigError(f"staff.{mid}: no working hours")
        lunch = parse_range(raw["lunch"], f"staff.{mid}.lunch") if raw.get("lunch") else None
        staff[mid] = Staff(mid, localized(raw.get("name"), f"staff.{mid}.name"), offered, hours, lunch)
    if not staff:
        raise ConfigError("no staff defined")
    for sid in services:
        if not any(sid in member.services for member in staff.values()):
            raise ConfigError(f"services.{sid}: nobody offers this service")

    raw_rules = data.get("rules", {})
    defaults = Rules()
    rules = Rules(
        slot_minutes=int(raw_rules.get("slot_minutes", defaults.slot_minutes)),
        min_lead_minutes=int(raw_rules.get("min_lead_minutes", defaults.min_lead_minutes)),
        horizon_days=int(raw_rules.get("horizon_days", defaults.horizon_days)),
        cancel_minutes=int(raw_rules.get("cancel_minutes", defaults.cancel_minutes)),
        max_active=int(raw_rules.get("max_active", defaults.max_active)),
        remind_hours=tuple(sorted((int(h) for h in raw_rules.get("remind_hours", defaults.remind_hours)), reverse=True)),
    )
    if rules.slot_minutes <= 0 or rules.horizon_days <= 0 or rules.horizon_days > 28:
        raise ConfigError("rules: slot_minutes must be positive and horizon_days between 1 and 28")

    return Business(
        name=str(data.get("name") or "bookbot"),
        phone=str(data.get("phone") or ""),
        tz=ZoneInfo(str(data.get("timezone") or "Asia/Almaty")),
        currency=str(data.get("currency") or "₸"),
        address=localized(data.get("address") or "", "address"),
        about=localized(data.get("about") or "", "about"),
        services=services,
        staff=staff,
        rules=rules,
    )


def load_business(path: Path) -> Business:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from None
    return parse_business(data)


def env_file() -> Path:
    explicit = os.environ.get("BOOKBOT_ENV")
    if explicit:
        return Path(explicit).expanduser()
    local = Path("env")
    return local if local.is_file() else Path.home() / ".config/bookbot/env"


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def load_settings() -> Settings:
    path = env_file()
    load_env(path)
    token = os.environ.get("BOT_TOKEN", "")
    if not token or "replace-me" in token:
        raise ConfigError(f"set BOT_TOKEN in {path}")
    try:
        admins = frozenset(int(x) for x in re.split(r"[,\s]+", os.environ.get("ADMIN_IDS", "")) if x)
    except ValueError:
        raise ConfigError("ADMIN_IDS must be numeric Telegram ids separated by commas") from None
    if not admins:
        raise ConfigError(f"set ADMIN_IDS in {path}")
    return Settings(
        token=token,
        admins=admins,
        business_file=Path(os.environ.get("BUSINESS_FILE", "business.toml")).expanduser(),
        db_file=Path(os.environ.get("DB_FILE", "bookbot.sqlite3")).expanduser(),
        proxy=os.environ.get("TELEGRAM_PROXY") or None,
    )
