"""外部协作台账的字段规范化和业务校验。"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bridgeboard.domain.errors import InvalidInput
from bridgeboard.domain.model import EventKind, Observation, canonical_payload, parse_timestamp


ALLOWED_PAYLOAD_FIELDS = {
    EventKind.INTRODUCED: {"origin", "note"},
    EventKind.PARTNER_MATCHED: {"partner_refs", "match_basis", "note"},
    EventKind.FEASIBILITY_STARTED: {"workstreams", "readiness", "note"},
    EventKind.AGREEMENT_SIGNED: {"agreement_ref", "agreement_scope", "note"},
    EventKind.IMPLEMENTATION_STARTED: {"site_ref", "investment_band", "note"},
    EventKind.OUTCOME_VERIFIED: {"outcome_type", "evidence_ref", "note"},
    EventKind.PAUSED: {"reason", "review_on", "note"},
    EventKind.RESUMED: {"reason", "note"},
    EventKind.CLOSED: {"reason", "note"},
}
REQUIRED_PAYLOAD_FIELDS = {
    EventKind.PARTNER_MATCHED: {"partner_refs"},
    EventKind.FEASIBILITY_STARTED: {"workstreams", "readiness"},
    EventKind.AGREEMENT_SIGNED: {"agreement_ref"},
    EventKind.IMPLEMENTATION_STARTED: {"site_ref"},
    EventKind.OUTCOME_VERIFIED: {"outcome_type", "evidence_ref"},
    EventKind.PAUSED: {"reason"},
    EventKind.CLOSED: {"reason"},
}
MAX_NOTE = 1000


def normalize_event(value: Any, source_system: str,
                    received_at: datetime | None = None) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidInput("事件必须为对象")
    required = {"project_id", "source_record_id", "revision", "kind",
                "occurred_at", "payload"}
    missing = sorted(required - value.keys())
    if missing:
        raise InvalidInput("事件缺少字段：" + ", ".join(missing))
    project_id = _identifier(value["project_id"], "project_id", 80)
    record_id = _identifier(value["source_record_id"], "source_record_id", 160)
    revision = value["revision"]
    if type(revision) is not int or revision < 1 or revision > 1_000_000:
        raise InvalidInput("revision 必须为正整数")
    try:
        kind = EventKind(value["kind"])
    except (ValueError, TypeError) as exc:
        raise InvalidInput("kind 不是支持的项目事件") from exc
    occurred_at = parse_timestamp(value["occurred_at"], "occurred_at")
    payload = validate_payload(kind, value["payload"])
    canonical = canonical_payload(payload)
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    received = received_at or datetime.now(timezone.utc)
    return {
        "id": str(uuid4()), "project_id": project_id,
        "source_system": _identifier(source_system, "source_system", 80),
        "source_record_id": record_id, "revision": revision,
        "kind": kind.value, "occurred_at": occurred_at.isoformat(),
        "received_at": received.astimezone(timezone.utc).isoformat(),
        "payload": canonical, "payload_hash": digest,
    }


def validate_payload(kind: EventKind, payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise InvalidInput("payload 必须为对象")
    allowed = ALLOWED_PAYLOAD_FIELDS[kind]
    unexpected = sorted(payload.keys() - allowed)
    if unexpected:
        raise InvalidInput("payload 含不支持的字段：" + ", ".join(unexpected))
    missing = REQUIRED_PAYLOAD_FIELDS.get(kind, set()) - payload.keys()
    if missing:
        raise InvalidInput("payload 缺少字段：" + ", ".join(sorted(missing)))
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        if key in {"note", "reason", "match_basis", "agreement_scope"}:
            cleaned[key] = _identifier(value, key, MAX_NOTE)
        elif key == "review_on":
            cleaned[key] = _date_string(value, key)
        elif key in {"workstreams", "partner_refs"}:
            cleaned[key] = _string_list(value, key)
        elif key == "readiness":
            if value not in {"unknown", "preparing", "ready", "blocked"}:
                raise InvalidInput("readiness 不在支持的状态中")
            cleaned[key] = value
        elif key == "investment_band":
            if value not in {"undisclosed", "under_1m", "1m_10m", "over_10m"}:
                raise InvalidInput("investment_band 不在支持的区间中")
            cleaned[key] = value
        else:
            cleaned[key] = _identifier(value, key, 200)
    if kind is EventKind.OUTCOME_VERIFIED:
        if not cleaned.get("evidence_ref") or not cleaned.get("outcome_type"):
            raise InvalidInput("已验证成果必须提供 outcome_type 和 evidence_ref")
    if kind is EventKind.PARTNER_MATCHED and not cleaned.get("partner_refs"):
        raise InvalidInput("合作匹配事件必须包含 partner_refs")
    if kind is EventKind.PAUSED and not cleaned.get("reason"):
        raise InvalidInput("暂停事件必须说明 reason")
    if kind is EventKind.CLOSED and not cleaned.get("reason"):
        raise InvalidInput("关闭事件必须说明 reason")
    return cleaned


def _identifier(value: Any, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise InvalidInput(f"{field} 必须为 1 至 {limit} 个字符")
    if any(ord(character) < 32 for character in value):
        raise InvalidInput(f"{field} 不能包含控制字符")
    return value.strip()


def _string_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 30:
        raise InvalidInput(f"{field} 必须包含 1 至 30 项")
    return list(dict.fromkeys(_identifier(item, field, 160) for item in value))


def _date_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise InvalidInput(f"{field} 必须为 YYYY-MM-DD")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError as exc:
        raise InvalidInput(f"{field} 必须为 YYYY-MM-DD") from exc
