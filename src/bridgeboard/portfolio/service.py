"""项目登记、业务查询与当前阶段投影。"""

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from bridgeboard.domain.errors import Conflict, InvalidInput
from bridgeboard.domain.model import ECONOMIES, SECTORS, EventKind, ProjectDraft
from bridgeboard.domain.transitions import timeline
from bridgeboard.portfolio import repository
from bridgeboard.portfolio.database import Database


class PortfolioService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create_project(self, values: dict[str, Any]) -> dict[str, Any]:
        draft = self._draft(values)
        now = datetime.now(timezone.utc).isoformat()
        project_id = str(uuid4())
        with self.database.transaction() as connection:
            project = repository.insert_project(connection, project_id, draft, now)
            event_id = str(uuid4())
            event = {
                "id": event_id, "project_id": project_id,
                "source_system": "bridgeboard-manual",
                "source_record_id": f"{project_id}:introduced", "revision": 1,
                "kind": EventKind.INTRODUCED.value,
                "occurred_at": datetime.combine(draft.opened_on, datetime.min.time(),
                                                 tzinfo=timezone.utc).isoformat(),
                "received_at": now, "payload": {"origin": "manual-registration"},
                "payload_hash": "manual:" + project_id,
            }
            repository.insert_observation(connection, event)
        return {**project, "stage": "discovery", "stage_entered_at": event["occurred_at"]}

    def get_project(self, project_id: str) -> dict[str, Any]:
        connection = self.database.read()
        try:
            project = repository.get_project(connection, project_id)
            events = active_timeline(repository.observations_for(connection, project_id))
        finally:
            connection.close()
        stages = timeline(events)
        current = stages[-1]
        return {**project, "stage": current.stage.value,
                "stage_entered_at": current.entered_at.isoformat(),
                "event_count": len(events),
                "verified_outcome": current.verified_outcome}

    def list_projects(self, sector: str | None = None,
                      economy: str | None = None) -> list[dict[str, Any]]:
        connection = self.database.read()
        try:
            projects = repository.list_projects(connection, sector=sector, economy=economy)
            events = repository.all_observations(connection)
        finally:
            connection.close()
        by_project: dict[str, list[dict]] = {}
        for event in events:
            by_project.setdefault(event["project_id"], []).append(event)
        result = []
        for project in projects:
            active = active_timeline(by_project.get(project["id"], []))
            states = timeline(active)
            current = states[-1]
            result.append({**project, "stage": current.stage.value,
                           "stage_entered_at": current.entered_at.isoformat(),
                           "event_count": len(active),
                           "verified_outcome": current.verified_outcome})
        return result

    @staticmethod
    def _draft(values: dict[str, Any]) -> ProjectDraft:
        required = ("title", "lead_economy", "partner_economies", "sector",
                    "coordinator", "source_ref", "opened_on")
        missing = [field for field in required if field not in values]
        if missing:
            raise InvalidInput("缺少项目字段：" + ", ".join(missing))
        title = _text(values["title"], "title", 180)
        lead = _choice(values["lead_economy"], ECONOMIES, "lead_economy")
        partners_value = values["partner_economies"]
        if not isinstance(partners_value, list) or not partners_value:
            raise InvalidInput("partner_economies 必须至少包含一个合作经济体")
        partners = tuple(dict.fromkeys(
            _choice(item, ECONOMIES, "partner_economies") for item in partners_value
        ))
        if lead in partners:
            raise InvalidInput("牵头经济体不能同时作为合作经济体")
        sector = _choice(values["sector"], SECTORS, "sector")
        coordinator = _text(values["coordinator"], "coordinator", 120)
        source_ref = _text(values["source_ref"], "source_ref", 160)
        opened = _date(values["opened_on"])
        return ProjectDraft(title, lead, partners, sector, coordinator, source_ref, opened)


def active_timeline(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """以每条来源记录最高修订版构成当前视图，旧版仍保留供审计。"""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for event in events:
        key = (event["source_system"], event["source_record_id"])
        previous = latest.get(key)
        if previous is None or event["revision"] > previous["revision"]:
            latest[key] = event
    return sorted(latest.values(), key=lambda item: (
        item["occurred_at"], item["source_system"], item["source_record_id"],
        item["revision"], item["id"],
    ))


def _text(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise InvalidInput(f"{field} 必须为 1 至 {limit} 个字符")
    return value.strip()


def _choice(value: Any, options: set[str], field: str) -> str:
    normalized = _text(value, field, 80)
    if normalized not in options:
        raise InvalidInput(f"{field} 不在当前业务目录中")
    return normalized


def _date(value: Any) -> date:
    if not isinstance(value, str):
        raise InvalidInput("opened_on 必须为 YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise InvalidInput("opened_on 必须为 YYYY-MM-DD") from exc
