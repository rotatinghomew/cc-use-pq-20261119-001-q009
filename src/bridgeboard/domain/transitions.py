"""项目阶段迁移规则与时间线解释。"""

from dataclasses import dataclass
from datetime import datetime

from .errors import Conflict
from .model import EVENT_STAGE, EventKind, Observation, Stage


ALLOWED: dict[Stage | None, set[EventKind]] = {
    None: {EventKind.INTRODUCED},
    Stage.DISCOVERY: {EventKind.PARTNER_MATCHED, EventKind.PAUSED, EventKind.CLOSED},
    Stage.MATCHED: {EventKind.FEASIBILITY_STARTED, EventKind.PAUSED, EventKind.CLOSED},
    Stage.FEASIBILITY: {EventKind.AGREEMENT_SIGNED, EventKind.PAUSED, EventKind.CLOSED},
    Stage.AGREEMENT: {EventKind.IMPLEMENTATION_STARTED, EventKind.PAUSED, EventKind.CLOSED},
    Stage.IMPLEMENTATION: {EventKind.OUTCOME_VERIFIED, EventKind.PAUSED, EventKind.CLOSED},
    Stage.PAUSED: {EventKind.RESUMED, EventKind.CLOSED},
    Stage.COMPLETED: set(),
    Stage.CLOSED: set(),
}


@dataclass(frozen=True)
class StageSnapshot:
    stage: Stage
    entered_at: datetime
    last_event_id: str
    verified_outcome: bool


def ordered(observations: list[dict]) -> list[dict]:
    return sorted(observations, key=lambda item: (
        item["occurred_at"], item["source_system"], item["source_record_id"],
        item["revision"], item["id"],
    ))


def timeline(observations: list[dict]) -> list[StageSnapshot]:
    snapshots: list[StageSnapshot] = []
    current: Stage | None = None
    paused_from: Stage | None = None
    for event in ordered(observations):
        kind = EventKind(event["kind"])
        if kind not in ALLOWED[current]:
            raise Conflict(
                f"事件 {kind.value} 不能从阶段 {current.value if current else 'empty'} 发生"
            )
        if kind is EventKind.PAUSED:
            paused_from = current
            current = Stage.PAUSED
        elif kind is EventKind.RESUMED:
            if paused_from is None:
                raise Conflict("暂停项目缺少可恢复的原阶段")
            current = paused_from
            paused_from = None
        else:
            current = EVENT_STAGE[kind]
        snapshots.append(StageSnapshot(
            stage=current,
            entered_at=datetime.fromisoformat(event["occurred_at"]),
            last_event_id=event["id"],
            verified_outcome=kind is EventKind.OUTCOME_VERIFIED,
        ))
    return snapshots


def validate_append(existing: list[dict], proposed: list[dict]) -> None:
    """在提交前检查并入排序后的完整时间线，不只检查最新事件。"""
    timeline(existing + proposed)


def elapsed_days(start: datetime, end: datetime) -> float:
    if end < start:
        raise Conflict("阶段结束时间早于开始时间")
    return (end - start).total_seconds() / 86400
