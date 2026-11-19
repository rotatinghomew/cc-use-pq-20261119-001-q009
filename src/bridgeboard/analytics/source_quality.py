"""导入来源的时效、重复和更正状况。"""

from collections import defaultdict
from datetime import date, datetime, timezone
from statistics import median
from typing import Any


def build_source_quality(events: list[dict[str, Any]],
                         batches: list[dict[str, Any]], *,
                         as_of: date) -> dict[str, Any]:
    """为分析使用者说明数据到达特征，不将到达慢误判为业务推进慢。"""
    events_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    batches_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        events_by_source[event["source_system"]].append(event)
    for batch in batches:
        batches_by_source[batch["source_system"]].append(batch)
    sources = sorted(set(events_by_source) | set(batches_by_source))
    summaries = [_source_summary(source, events_by_source[source],
                                 batches_by_source[source], as_of)
                 for source in sources]
    return {
        "as_of": as_of.isoformat(),
        "definition": "到达延迟按事件发生时间至服务接收时间计算；修订数仅用于提示事实更正频率，不代表业务质量评级。",
        "source_count": len(summaries),
        "event_count": len(events),
        "batch_count": len(batches),
        "sources": summaries,
        "alerts": _alerts(summaries),
    }


def _source_summary(source: str, events: list[dict[str, Any]],
                    batches: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    delays = [_delay(event) for event in events]
    corrections = sum(max(0, event["revision"] - 1) for event in events)
    duplicates = sum(batch["duplicate_count"] for batch in batches)
    reported = sum(batch["record_count"] for batch in batches)
    accepted = sum(batch["accepted_count"] for batch in batches)
    late = [event for event in events if _delay(event) > 7]
    last_received = max((event["received_at"] for event in events), default=None)
    days_since_receipt = None
    if last_received:
        days_since_receipt = max(0, (as_of - datetime.fromisoformat(last_received).date()).days)
    return {
        "source_system": source,
        "received_events": len(events), "batches": len(batches),
        "reported_records": reported, "accepted_records": accepted,
        "duplicate_records": duplicates,
        "duplicate_share": _rate(duplicates, reported),
        "revised_facts": corrections,
        "median_arrival_delay_days": round(median(delays), 2) if delays else None,
        "p90_arrival_delay_days": round(_percentile(delays, .9), 2) if delays else None,
        "events_over_seven_days_late": len(late),
        "last_received_at": last_received,
        "days_since_last_receipt": days_since_receipt,
        "late_examples": [{"source_record_id": event["source_record_id"],
                           "project_id": event["project_id"],
                           "occurred_at": event["occurred_at"],
                           "received_at": event["received_at"]}
                          for event in sorted(late, key=_delay, reverse=True)[:5]],
    }


def _delay(event: dict[str, Any]) -> float:
    occurred = datetime.fromisoformat(event["occurred_at"])
    received = datetime.fromisoformat(event["received_at"])
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    if received.tzinfo is None:
        received = received.replace(tzinfo=timezone.utc)
    return max(0.0, (received - occurred).total_seconds() / 86400)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    position = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * percentile)))
    return ordered[position]


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _alerts(sources: list[dict[str, Any]]) -> list[dict[str, str]]:
    alerts = []
    for source in sources:
        name = source["source_system"]
        if source["events_over_seven_days_late"]:
            alerts.append({"source_system": name, "kind": "delayed_arrival",
                           "message": f"有 {source['events_over_seven_days_late']} 条事件晚于发生后一周到达。"})
        if source["revised_facts"]:
            alerts.append({"source_system": name, "kind": "revisions",
                           "message": f"发现 {source['revised_facts']} 条后续修订事实，相关时间线及指标按最新修订计算。"})
        if source["duplicate_records"]:
            alerts.append({"source_system": name, "kind": "duplicates",
                           "message": f"批次中有 {source['duplicate_records']} 条重复记录，已按来源版本去重。"})
    return alerts
