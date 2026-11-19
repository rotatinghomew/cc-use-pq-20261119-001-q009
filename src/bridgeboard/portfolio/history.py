"""可回查的项目事实与来源版本历史。"""

from typing import Any

from bridgeboard.domain.errors import NotFound
from bridgeboard.portfolio import repository
from bridgeboard.portfolio.database import Database
from bridgeboard.portfolio.service import active_timeline


class HistoryService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def project_history(self, project_id: str) -> dict[str, Any]:
        connection = self.database.read()
        try:
            project = repository.get_project(connection, project_id)
            events = repository.observations_for(connection, project_id)
            batches = repository.all_batches(connection)
            batch_items = self._items_by_observation(connection)
        finally:
            connection.close()
        active_ids = {event["id"] for event in active_timeline(events)}
        timeline = []
        for event in sorted(events, key=lambda item: (
            item["occurred_at"], item["source_system"],
            item["source_record_id"], item["revision"],
        )):
            timeline.append({
                "event_id": event["id"], "source_system": event["source_system"],
                "source_record_id": event["source_record_id"],
                "revision": event["revision"], "kind": event["kind"],
                "occurred_at": event["occurred_at"],
                "received_at": event["received_at"], "payload": event["payload"],
                "current_revision": event["id"] in active_ids,
                "batches": batch_items.get(event["id"], []),
            })
        relevant_batch_ids = {batch_id for event in timeline for batch_id in event["batches"]}
        relevant_batches = [
            {"id": batch["id"], "source_system": batch["source_system"],
             "received_at": batch["received_at"], "record_count": batch["record_count"],
             "accepted_count": batch["accepted_count"],
             "duplicate_count": batch["duplicate_count"]}
            for batch in batches if batch["id"] in relevant_batch_ids
        ]
        return {"project": project, "timeline": timeline,
                "revision_count": sum(not event["current_revision"] for event in timeline),
                "batches": relevant_batches}

    @staticmethod
    def _items_by_observation(connection) -> dict[str, list[str]]:
        rows = connection.execute(
            "SELECT batch_id, observation_id FROM batch_items WHERE observation_id IS NOT NULL"
        ).fetchall()
        result: dict[str, list[str]] = {}
        for row in rows:
            result.setdefault(row["observation_id"], []).append(row["batch_id"])
        return result
