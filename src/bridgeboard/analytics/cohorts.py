"""项目启动批次的推进与成果分析。"""

from collections import defaultdict
from datetime import date, datetime
from statistics import median
from typing import Any

from bridgeboard.domain.model import EventKind
from bridgeboard.portfolio.service import active_timeline


def build_cohorts(projects: list[dict[str, Any]],
                  observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按启动月份组织项目，以避免把不同成熟度的项目直接横向对比。"""
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in observations:
        by_project[event["project_id"]].append(event)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in projects:
        month = date.fromisoformat(project["opened_on"]).strftime("%Y-%m")
        groups[month].append(project)
    output = []
    for month, cohort in sorted(groups.items()):
        facts = [_cohort_project(project, by_project.get(project["id"], []))
                 for project in cohort]
        closed = sum(item["closed"] for item in facts)
        verified = sum(item["verified"] for item in facts)
        match_delays = [item["days_to_match"] for item in facts
                        if item["days_to_match"] is not None]
        outcome_durations = [item["days_to_verified_outcome"] for item in facts
                             if item["days_to_verified_outcome"] is not None]
        output.append({
            "opened_month": month, "project_count": len(cohort),
            "currently_active": len(cohort) - closed,
            "closed_or_completed": closed, "verified_outcomes": verified,
            "verified_outcome_rate_of_closed": _rate(verified, closed),
            "matched_projects": len(match_delays),
            "median_days_to_match": round(median(match_delays), 2) if match_delays else None,
            "projects_with_verified_duration": len(outcome_durations),
            "median_days_to_verified_outcome": round(median(outcome_durations), 2)
            if outcome_durations else None,
            "interpretation": _cohort_note(len(cohort), closed, len(match_delays)),
        })
    return output


def _cohort_project(project: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    active = active_timeline(events)
    first_match = next((event for event in active
                        if event["kind"] == EventKind.PARTNER_MATCHED.value), None)
    verified_event = next((event for event in reversed(active)
                           if event["kind"] == EventKind.OUTCOME_VERIFIED.value), None)
    latest = active[-1] if active else None
    opened = date.fromisoformat(project["opened_on"])
    match_delay = _calendar_days(opened, first_match["occurred_at"]) if first_match else None
    outcome_delay = _calendar_days(opened, verified_event["occurred_at"]) if verified_event else None
    return {"closed": latest is not None and latest["kind"] in {
                EventKind.CLOSED.value, EventKind.OUTCOME_VERIFIED.value},
            "verified": latest is not None and latest["kind"] == EventKind.OUTCOME_VERIFIED.value,
            "days_to_match": match_delay,
            "days_to_verified_outcome": outcome_delay}


def _calendar_days(start: date, timestamp: str) -> int:
    event_date = datetime.fromisoformat(timestamp).date()
    return max(0, (event_date - start).days)


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _cohort_note(total: int, closed: int, matched: int) -> list[str]:
    notes = []
    if total < 5:
        notes.append("启动月份样本少于 5 个项目，不宜据此比较合作成效。")
    if closed == 0:
        notes.append("该批项目尚无关闭或成果核实记录，成果比例为空。")
    if matched == 0:
        notes.append("该批项目尚无伙伴匹配记录，无法计算匹配耗时。")
    return notes
