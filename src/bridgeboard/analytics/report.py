"""项目组合指标、阶段耗时与数据充分性说明。"""

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any

from bridgeboard.domain.errors import InvalidInput
from bridgeboard.domain.model import Stage
from bridgeboard.domain.transitions import elapsed_days, timeline
from bridgeboard.analytics.funnel import build_funnel, stage_reach_by_dimension
from bridgeboard.analytics.cohorts import build_cohorts
from bridgeboard.analytics.transitions import build_transition_analysis
from bridgeboard.analytics.cohorts import build_cohorts
from bridgeboard.portfolio.service import active_timeline


FINAL_STAGES = {Stage.COMPLETED, Stage.CLOSED}
DEFAULT_STALE_DAYS = 90


def build_report(projects: list[dict[str, Any]], events: list[dict[str, Any]], *,
                 as_of: date, sector: str | None = None,
                 economy: str | None = None, opened_from: date | None = None,
                 opened_to: date | None = None,
                 stale_after_days: int = DEFAULT_STALE_DAYS) -> dict[str, Any]:
    if stale_after_days < 1 or stale_after_days > 3650:
        raise InvalidInput("stale_after_days 必须在 1 至 3650 之间")
    selected = _select_projects(projects, sector, economy, opened_from, opened_to)
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_project[event["project_id"]].append(event)
    rows = [_project_facts(project, by_project.get(project["id"], []), as_of)
            for project in selected]
    stages = Counter(row["stage"] for row in rows)
    sectors = _dimension(rows, "sector")
    economies = _economy_dimension(rows)
    age_groups = _aging(rows, stale_after_days)
    stage_durations = _durations(rows)
    verified = sum(row["verified_outcome"] for row in rows)
    mature = sum(row["stage"] in FINAL_STAGES for row in rows)
    return {
        "as_of": as_of.isoformat(),
        "filters": {"sector": sector, "economy": economy,
                    "opened_from": opened_from.isoformat() if opened_from else None,
                    "opened_to": opened_to.isoformat() if opened_to else None,
                    "stale_after_days": stale_after_days},
        "portfolio": {
            "project_count": len(rows),
            "stage_counts": {stage.value: stages.get(stage.value, 0) for stage in Stage},
            "verified_outcomes": verified,
            "closed_or_completed": mature,
            "verified_outcome_rate_of_closed": _rate(verified, mature),
            "outcome_rate_note": "仅以已关闭或成果已验证项目为分母；未结束项目不计作失败",
        },
        "by_sector": sectors,
        "by_economy": economies,
        "funnel": build_funnel(selected, events),
        "funnel_by_sector": stage_reach_by_dimension(selected, events, "sector"),
        "funnel_by_lead_economy": stage_reach_by_dimension(selected, events, "lead_economy"),
        "opening_cohorts": build_cohorts(selected, events),
        "transition_analysis": build_transition_analysis(selected, events),
        "opening_cohorts": build_cohorts(selected, events),
        "aging": age_groups,
        "stage_durations": stage_durations,
        "projects": rows,
        "interpretation": _interpret(rows, age_groups, stage_durations),
    }


def _select_projects(projects: list[dict[str, Any]], sector: str | None,
                     economy: str | None, opened_from: date | None,
                     opened_to: date | None) -> list[dict[str, Any]]:
    if opened_from and opened_to and opened_from > opened_to:
        raise InvalidInput("opened_from 不能晚于 opened_to")
    selected = []
    for project in projects:
        opened = date.fromisoformat(project["opened_on"])
        if sector and project["sector"] != sector:
            continue
        if economy and economy not in project["partner_economies"] and project["lead_economy"] != economy:
            continue
        if opened_from and opened < opened_from:
            continue
        if opened_to and opened > opened_to:
            continue
        selected.append(project)
    return sorted(selected, key=lambda item: (item["opened_on"], item["id"]))


def _project_facts(project: dict[str, Any], events: list[dict[str, Any]],
                   as_of: date) -> dict[str, Any]:
    active = active_timeline(events)
    states = timeline(active)
    current = states[-1]
    entered = current.entered_at.astimezone(timezone.utc)
    days_in_stage = max(0, (as_of - entered.date()).days)
    stage_spans: dict[str, list[float]] = defaultdict(list)
    for index, state in enumerate(states):
        end = states[index + 1].entered_at if index + 1 < len(states) else None
        if end is None:
            continue
        stage = state.stage.value
        if state.stage not in FINAL_STAGES and state.stage is not Stage.PAUSED:
            stage_spans[stage].append(elapsed_days(state.entered_at, end))
    verified = current.verified_outcome
    final = current.stage in FINAL_STAGES
    return {
        "id": project["id"], "title": project["title"],
        "lead_economy": project["lead_economy"],
        "partner_economies": project["partner_economies"],
        "sector": project["sector"], "coordinator": project["coordinator"],
        "opened_on": project["opened_on"], "stage": current.stage.value,
        "stage_entered_at": entered.isoformat(), "days_in_stage": days_in_stage,
        "event_count": len(active), "verified_outcome": verified,
        "outcome_evidence_present": bool(
            active[-1]["payload"].get("evidence_ref") if verified else False
        ),
        "closed_or_completed": final,
        "stage_spans": {key: values for key, values in stage_spans.items()},
        "source_revisions": len(events) - len(active),
    }


def _dimension(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row[field]].append(row)
    return [_group_summary(key, values) for key, values in sorted(grouped.items())]


def _economy_dimension(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for economy in set([row["lead_economy"], *row["partner_economies"]]):
            grouped[economy].append(row)
    return [_group_summary(key, values) for key, values in sorted(grouped.items())]


def _group_summary(key: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    complete = sum(row["verified_outcome"] for row in rows)
    closed = sum(row["closed_or_completed"] for row in rows)
    stage_counts = Counter(row["stage"] for row in rows)
    return {"key": key, "project_count": len(rows),
            "verified_outcomes": complete, "closed_or_completed": closed,
            "verified_outcome_rate_of_closed": _rate(complete, closed),
            "stage_counts": dict(sorted(stage_counts.items()))}


def _aging(rows: list[dict[str, Any]], threshold: int) -> dict[str, Any]:
    active = [row for row in rows if row["stage"] not in {stage.value for stage in FINAL_STAGES}]
    stale = [row for row in active if row["days_in_stage"] >= threshold]
    return {
        "active_project_count": len(active), "threshold_days": threshold,
        "stale_project_count": len(stale),
        "stale_rate": _rate(len(stale), len(active)),
        "by_stage": [
            {"stage": stage.value,
             "active_count": sum(row["stage"] == stage.value for row in active),
             "stale_count": sum(row["stage"] == stage.value and row["days_in_stage"] >= threshold
                                 for row in active)}
            for stage in Stage if any(row["stage"] == stage.value for row in active)
        ],
        "projects": [{"id": row["id"], "title": row["title"],
                      "stage": row["stage"], "days_in_stage": row["days_in_stage"]}
                     for row in stale],
    }


def _durations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    collected: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for stage, values in row["stage_spans"].items():
            collected[stage].extend(values)
    return [{"stage": stage, "completed_observations": len(values),
             "mean_days": round(sum(values) / len(values), 2),
             "median_days": round(sorted(values)[(len(values) - 1) // 2], 2)}
            for stage, values in sorted(collected.items()) if values]


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _interpret(rows: list[dict[str, Any]], aging: dict[str, Any],
               durations: list[dict[str, Any]]) -> list[dict[str, str]]:
    notes = []
    if not rows:
        return [{"kind": "insufficient_data", "message": "当前筛选条件下没有项目，无法形成组合判断。"}]
    if aging["active_project_count"] == 0:
        notes.append({"kind": "no_active_projects", "message": "当前组合没有进行中项目，阶段停留指标不适用。"})
    elif aging["stale_project_count"]:
        notes.append({"kind": "aging", "message": f"有 {aging['stale_project_count']} 个进行中项目达到停留阈值，可优先核对其协调进展。"})
    if not durations:
        notes.append({"kind": "insufficient_history", "message": "尚无完整阶段区间，不展示阶段平均耗时。"})
    for group in _dimension(rows, "sector"):
        if group["project_count"] < 3:
            notes.append({"kind": "small_cohort", "message": f"{group['key']} 领域仅有 {group['project_count']} 个项目，分组结果仅作线索。"})
    if not any(row["verified_outcome"] for row in rows):
        notes.append({"kind": "no_verified_outcomes", "message": "没有已登记的成果证据；不可将未完成项目解释为零成果或失败。"})
    return notes
