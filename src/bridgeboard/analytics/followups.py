"""可解释的项目协调跟进队列。"""

from datetime import date, datetime
from typing import Any

from bridgeboard.domain.model import Stage
from bridgeboard.domain.transitions import timeline
from bridgeboard.portfolio.service import active_timeline


ACTIVE_STAGES = {Stage.DISCOVERY, Stage.MATCHED, Stage.FEASIBILITY,
                 Stage.AGREEMENT, Stage.IMPLEMENTATION}
STAGE_THRESHOLDS = {
    Stage.DISCOVERY: 30, Stage.MATCHED: 45, Stage.FEASIBILITY: 60,
    Stage.AGREEMENT: 60, Stage.IMPLEMENTATION: 90,
}


def build_followups(projects: list[dict[str, Any]],
                    observations: list[dict[str, Any]], *,
                    as_of: date, stale_after_days: int = 90) -> dict[str, Any]:
    by_project: dict[str, list[dict[str, Any]]] = {}
    for event in observations:
        by_project.setdefault(event["project_id"], []).append(event)
    queue = []
    for project in projects:
        events = active_timeline(by_project.get(project["id"], []))
        if not events:
            continue
        states = timeline(events)
        current = states[-1]
        stage = current.stage
        days = max(0, (as_of - current.entered_at.date()).days)
        latest = events[-1]
        reasons = _reasons(stage, days, latest, as_of, stale_after_days)
        if not reasons:
            continue
        priority = _priority(stage, days, reasons)
        queue.append({
            "project_id": project["id"], "title": project["title"],
            "coordinator": project["coordinator"], "sector": project["sector"],
            "stage": stage.value, "days_in_stage": days,
            "priority": priority, "reasons": reasons,
            "last_business_update": latest["occurred_at"],
        })
    queue.sort(key=lambda item: (-item["priority"], -item["days_in_stage"], item["project_id"]))
    return {
        "as_of": as_of.isoformat(),
        "stage_thresholds_days": {stage.value: days for stage, days in STAGE_THRESHOLDS.items()},
        "default_threshold_days": stale_after_days,
        "candidate_count": len(queue), "items": queue,
        "definition": "队列仅提示达到阶段停留阈值、可行性阻塞或暂停复核日已到的项目；不替代协调人判断。",
    }


def _reasons(stage: Stage, days: int, event: dict[str, Any], as_of: date,
             default_threshold: int) -> list[dict[str, str]]:
    reasons = []
    if stage in ACTIVE_STAGES:
        threshold = STAGE_THRESHOLDS.get(stage, default_threshold)
        if days >= threshold:
            reasons.append({"kind": "stage_aging", "message": f"当前阶段已停留 {days} 天，超过 {threshold} 天关注线。"})
    if stage is Stage.FEASIBILITY and event["payload"].get("readiness") == "blocked":
        reasons.append({"kind": "readiness_blocked", "message": "可行性评估记录为受阻，需协调责任方确认依赖事项。"})
    if stage is Stage.PAUSED:
        review_on = event["payload"].get("review_on")
        if review_on and date.fromisoformat(review_on) <= as_of:
            reasons.append({"kind": "pause_review_due", "message": f"暂停复核日期 {review_on} 已到。"})
    return reasons


def _priority(stage: Stage, days: int, reasons: list[dict[str, str]]) -> int:
    weight = {Stage.DISCOVERY: 1, Stage.MATCHED: 2, Stage.FEASIBILITY: 3,
              Stage.AGREEMENT: 3, Stage.IMPLEMENTATION: 2,
              Stage.PAUSED: 2}.get(stage, 0)
    urgency = min(30, max(0, days // 10))
    blocked = 20 if any(item["kind"] == "readiness_blocked" for item in reasons) else 0
    due = 15 if any(item["kind"] == "pause_review_due" for item in reasons) else 0
    return weight * 10 + urgency + blocked + due
