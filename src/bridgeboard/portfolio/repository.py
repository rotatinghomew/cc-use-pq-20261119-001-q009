"""组合与事件的 SQL 读写适配。"""

import json
import sqlite3
from typing import Any

from bridgeboard.domain.errors import Conflict, NotFound
from bridgeboard.domain.model import ProjectDraft


def insert_project(connection: sqlite3.Connection, project_id: str,
                   draft: ProjectDraft, created_at: str) -> dict[str, Any]:
    try:
        connection.execute(
            "INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (project_id, draft.title, draft.lead_economy,
             json.dumps(draft.partner_economies, ensure_ascii=False), draft.sector,
             draft.coordinator, draft.source_ref, draft.opened_on.isoformat(), created_at),
        )
    except sqlite3.IntegrityError as exc:
        raise Conflict("项目来源编号已登记") from exc
    return get_project(connection, project_id)


def get_project(connection: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if row is None:
        raise NotFound("未找到合作项目")
    result = dict(row)
    result["partner_economies"] = json.loads(result["partner_economies"])
    return result


def find_project_by_source(connection: sqlite3.Connection, source_ref: str):
    return connection.execute("SELECT id FROM projects WHERE source_ref=?", (source_ref,)).fetchone()


def list_projects(connection: sqlite3.Connection, *, sector: str | None = None,
                  economy: str | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[str] = []
    if sector:
        clauses.append("sector=?")
        values.append(sector)
    if economy:
        clauses.append("(lead_economy=? OR partner_economies LIKE ?)")
        values.extend((economy, f'%"{economy}"%'))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    rows = connection.execute(
        "SELECT * FROM projects" + where + " ORDER BY opened_on, id", values
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["partner_economies"] = json.loads(item["partner_economies"])
        result.append(item)
    return result


def observations_for(connection: sqlite3.Connection, project_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM observations WHERE project_id=? ORDER BY occurred_at, id",
        (project_id,),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        result.append(item)
    return result


def all_observations(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM observations ORDER BY project_id, occurred_at, id"
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        result.append(item)
    return result


def insert_observation(connection: sqlite3.Connection, event: dict[str, Any]) -> None:
    try:
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event["id"], event["project_id"], event["source_system"],
             event["source_record_id"], event["revision"], event["kind"],
             event["occurred_at"], event["received_at"],
             json.dumps(event["payload"], ensure_ascii=False, sort_keys=True),
             event["payload_hash"]),
        )
    except sqlite3.IntegrityError as exc:
        raise Conflict("来源记录版本已存在") from exc


def source_revision(connection: sqlite3.Connection, source: str, record: str):
    return connection.execute(
        "SELECT revision, payload_hash, project_id FROM observations "
        "WHERE source_system=? AND source_record_id=? ORDER BY revision DESC LIMIT 1",
        (source, record),
    ).fetchone()


def save_batch(connection: sqlite3.Connection, batch: dict[str, Any],
               items: list[dict[str, Any]]) -> None:
    connection.execute(
        "INSERT INTO import_batches VALUES (?, ?, ?, ?, ?, ?, ?)",
        (batch["id"], batch["source_system"], batch["received_at"],
         batch["record_count"], batch["accepted_count"], batch["duplicate_count"],
         batch["digest"]),
    )
    connection.executemany(
        "INSERT INTO batch_items VALUES (?, ?, ?, ?, ?)",
        [(batch["id"], index, item.get("observation_id"), item["disposition"],
          item.get("detail", "")) for index, item in enumerate(items)],
    )


def get_batch(connection: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM import_batches WHERE id=?", (batch_id,)).fetchone()
    if row is None:
        raise NotFound("未找到导入批次")
    items = connection.execute(
        "SELECT ordinal, observation_id, disposition, detail FROM batch_items "
        "WHERE batch_id=? ORDER BY ordinal", (batch_id,),
    ).fetchall()
    return {**dict(row), "items": [dict(item) for item in items]}


def all_batches(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM import_batches ORDER BY received_at, id"
    ).fetchall()
    return [dict(row) for row in rows]
