"""领域值和状态词汇；不依赖 HTTP 或数据库。"""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any

from .errors import InvalidInput


class Stage(StrEnum):
    DISCOVERY = "discovery"
    MATCHED = "matched"
    FEASIBILITY = "feasibility"
    AGREEMENT = "agreement"
    IMPLEMENTATION = "implementation"
    COMPLETED = "completed"
    PAUSED = "paused"
    CLOSED = "closed"


class EventKind(StrEnum):
    INTRODUCED = "introduced"
    PARTNER_MATCHED = "partner_matched"
    FEASIBILITY_STARTED = "feasibility_started"
    AGREEMENT_SIGNED = "agreement_signed"
    IMPLEMENTATION_STARTED = "implementation_started"
    OUTCOME_VERIFIED = "outcome_verified"
    PAUSED = "paused"
    RESUMED = "resumed"
    CLOSED = "closed"


EVENT_STAGE: dict[EventKind, Stage] = {
    EventKind.INTRODUCED: Stage.DISCOVERY,
    EventKind.PARTNER_MATCHED: Stage.MATCHED,
    EventKind.FEASIBILITY_STARTED: Stage.FEASIBILITY,
    EventKind.AGREEMENT_SIGNED: Stage.AGREEMENT,
    EventKind.IMPLEMENTATION_STARTED: Stage.IMPLEMENTATION,
    EventKind.OUTCOME_VERIFIED: Stage.COMPLETED,
    EventKind.PAUSED: Stage.PAUSED,
    EventKind.RESUMED: Stage.IMPLEMENTATION,
    EventKind.CLOSED: Stage.CLOSED,
}

ECONOMIES = {
    "Australia", "Canada", "China", "Indonesia", "Japan", "Malaysia",
    "New Zealand", "Philippines", "Republic of Korea", "Singapore",
    "Thailand", "United States", "Vietnam",
}
SECTORS = {"advanced_manufacturing", "agriculture", "digital", "health",
           "logistics", "trade", "green_energy", "other"}


@dataclass(frozen=True)
class ProjectDraft:
    title: str
    lead_economy: str
    partner_economies: tuple[str, ...]
    sector: str
    coordinator: str
    source_ref: str
    opened_on: date


@dataclass(frozen=True)
class Observation:
    project_id: str
    source_system: str
    source_record_id: str
    revision: int
    kind: EventKind
    occurred_at: datetime
    received_at: datetime
    payload: dict[str, Any]


def parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise InvalidInput(f"{field} 必须为 YYYY-MM-DD") from exc


def parse_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise InvalidInput(f"{field} 必须为带时区的 ISO 8601 时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidInput(f"{field} 必须包含时区")
    return parsed.astimezone(timezone.utc)


def canonical_payload(value: Any) -> Any:
    """把 JSON 可表达值转成稳定摘要，避免键序造成重复判定差异。"""
    if isinstance(value, dict):
        return {str(key): canonical_payload(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonical_payload(item) for item in value]
    if isinstance(value, float) and not value.is_integer():
        return round(value, 8)
    return value
