"""批次预检、修订解释和全有或全无导入。"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bridgeboard.domain.errors import BatchRejected, Conflict, InvalidInput, NotFound
from bridgeboard.domain.transitions import validate_append
from bridgeboard.intake.normalization import normalize_event
from bridgeboard.portfolio import repository
from bridgeboard.portfolio.database import Database
from bridgeboard.portfolio.service import active_timeline


class IntakeService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def import_events(self, source_system: str,
                      records: list[dict[str, Any]]) -> dict[str, Any]:
        if not records:
            raise Conflict("导入批次不能为空")
        if len(records) > 500:
            raise Conflict("单批最多接收 500 条记录")
        received = datetime.now(timezone.utc)
        normalized: list[dict[str, Any]] = []
        issues: list[dict[str, str]] = []
        for index, record in enumerate(records):
            try:
                normalized.append(normalize_event(record, source_system, received))
            except InvalidInput as exc:
                issues.append({"index": str(index), "reason": str(exc)})
        if issues:
            raise BatchRejected(issues)
        digest = _batch_digest(normalized)
        batch_id = str(uuid4())
        with self.database.transaction() as connection:
            if connection.execute("SELECT 1 FROM import_batches WHERE digest=?", (digest,)).fetchone():
                existing = connection.execute(
                    "SELECT id FROM import_batches WHERE digest=?", (digest,)
                ).fetchone()
                from bridgeboard.portfolio.repository import get_batch
                return get_batch(connection, existing["id"])
            decisions, proposed = self._preflight(connection, normalized)
            if decisions["issues"]:
                raise BatchRejected(decisions["issues"])
            for event in decisions["accepted"]:
                repository.insert_observation(connection, event)
            repository.save_batch(connection, {
                "id": batch_id, "source_system": source_system,
                "received_at": received.isoformat(), "record_count": len(records),
                "accepted_count": len(decisions["accepted"]),
                "duplicate_count": len(decisions["duplicates"]), "digest": digest,
            }, decisions["items"])
            from bridgeboard.portfolio.repository import get_batch
            return get_batch(connection, batch_id)

    def _preflight(self, connection, events: list[dict[str, Any]]) -> tuple[dict, dict]:
        accepted: list[dict] = []
        duplicates: list[dict] = []
        issues: list[dict[str, str]] = []
        items: list[dict[str, Any]] = []
        seen: dict[tuple[str, str, int], dict] = {}
        per_project: dict[str, list[dict]] = {}
        latest_revision: dict[tuple[str, str], int] = {}
        baseline_by_project: dict[str, list[dict]] = {}
        for event in events:
            key = (event["source_system"], event["source_record_id"], event["revision"])
            if key in seen:
                if seen[key]["payload_hash"] == event["payload_hash"] and seen[key]["project_id"] == event["project_id"]:
                    duplicates.append(event)
                    items.append({"observation_id": seen[key]["id"], "disposition": "duplicate"})
                else:
                    issues.append(_issue(event, "同一批次内来源版本内容冲突"))
                continue
            seen[key] = event
            try:
                repository.get_project(connection, event["project_id"])
            except NotFound:
                issues.append(_issue(event, "引用的项目不存在"))
                continue
            revision_key = (event["source_system"], event["source_record_id"])
            if revision_key not in latest_revision:
                current = repository.source_revision(connection, *revision_key)
                latest_revision[revision_key] = current["revision"] if current else 0
                if current:
                    existing = connection.execute(
                        "SELECT * FROM observations WHERE source_system=? AND source_record_id=? ORDER BY revision",
                        revision_key,
                    ).fetchall()
                    for row in existing:
                        if row["project_id"] != event["project_id"]:
                            issues.append(_issue(event, "来源记录不能转移到另一个项目"))
                            break
            current_revision = latest_revision[revision_key]
            if event["revision"] <= current_revision:
                current = connection.execute(
                    "SELECT id, payload_hash, project_id FROM observations "
                    "WHERE source_system=? AND source_record_id=? AND revision=?",
                    (event["source_system"], event["source_record_id"], event["revision"]),
                ).fetchone()
                if current and current["payload_hash"] == event["payload_hash"] and current["project_id"] == event["project_id"]:
                    duplicates.append(event)
                    items.append({"observation_id": current["id"], "disposition": "duplicate"})
                else:
                    issues.append(_issue(event, "修订号必须递增，且不可重写已登记版本"))
                continue
            expected = current_revision + 1
            if event["revision"] != expected:
                issues.append(_issue(event, f"修订号应连续递增至 {expected}"))
                continue
            latest_revision[revision_key] = event["revision"]
            accepted.append(event)
            per_project.setdefault(event["project_id"], []).append(event)
            items.append({"observation_id": event["id"], "disposition": "accepted"})
        for project_id, proposed in per_project.items():
            if any(issue.get("project_id") == project_id for issue in issues):
                continue
            existing = repository.observations_for(connection, project_id)
            candidate = active_timeline(existing + proposed)
            try:
                validate_append([], candidate)
            except Exception as exc:
                issues.append({"project_id": project_id, "reason": str(exc)})
        return {"accepted": accepted, "duplicates": duplicates,
                "issues": issues, "items": items}, per_project


def _batch_digest(events: list[dict[str, Any]]) -> str:
    values = [{key: event[key] for key in (
        "project_id", "source_system", "source_record_id", "revision", "kind",
        "occurred_at", "payload_hash",
    )} for event in events]
    encoded = json.dumps(values, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _issue(event: dict[str, Any], reason: str) -> dict[str, str]:
    return {"project_id": event["project_id"],
            "source_record_id": event["source_record_id"], "reason": reason}
