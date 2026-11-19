"""项目阶段漏斗及阶段转化边界。"""

from collections import defaultdict
from typing import Any

from bridgeboard.domain.model import EventKind, Stage
from bridgeboard.domain.transitions import timeline
from bridgeboard.portfolio.service import active_timeline


FUNNEL = [Stage.DISCOVERY, Stage.MATCHED, Stage.FEASIBILITY,
          Stage.AGREEMENT, Stage.IMPLEMENTATION, Stage.COMPLETED]


def build_funnel(projects: list[dict[str, Any]],
                 observations: list[dict[str, Any]]) -> dict[str, Any]:
    """描述曾到达各阶段的项目数；不把当前阶段数当作累计到达数。"""
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in observations:
        by_project[event["project_id"]].append(event)
    project_stages: dict[str, set[Stage]] = {}
    terminal_stages: dict[str, Stage] = {}
    for project in projects:
        events = active_timeline(by_project.get(project["id"], []))
        reached: set[Stage] = set()
        if not events:
            reached.add(Stage.DISCOVERY)
        states = timeline(events)
        if states:
            terminal_stages[project["id"]] = states[-1].stage
        for state in states:
            if state.stage is not Stage.PAUSED and state.stage is not Stage.CLOSED:
                reached.add(state.stage)
        project_stages[project["id"]] = reached
    total = len(projects)
    stages = []
    previous_count: int | None = None
    for stage in FUNNEL:
        count = sum(stage in reached for reached in project_stages.values())
        eligible = previous_count if previous_count is not None else total
        stages.append({
            "stage": stage.value, "projects_reached": count,
            "share_of_all_projects": _rate(count, total),
            "conversion_from_prior_stage": _rate(count, eligible),
            "prior_stage_denominator": eligible,
        })
        previous_count = count
    paused = sum(Stage.PAUSED in reached for reached in project_stages.values())
    closed = sum(stage is Stage.CLOSED for stage in terminal_stages.values())
    return {
        "definition": "按当前有效修订时间线统计曾到达阶段的唯一项目；暂停与关闭另列，不作为推进漏斗阶段。",
        "project_count": total, "stages": stages,
        "paused_projects": paused, "closed_projects": closed,
        "data_note": _note(total, stages),
    }


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _note(total: int, stages: list[dict[str, Any]]) -> list[str]:
    notes = []
    if not total:
        notes.append("没有项目记录，漏斗比例不可计算。")
    if any(item["prior_stage_denominator"] == 0 for item in stages[1:]):
        notes.append("部分阶段没有前一阶段项目作为分母，转化比例返回空值。")
    if total < 5:
        notes.append("组合样本量较小，阶段比例仅供排查流程使用。")
    return notes


def stage_reach_by_dimension(projects: list[dict[str, Any]],
                             observations: list[dict[str, Any]],
                             field: str) -> list[dict[str, Any]]:
    """为行业或牵头经济体拆分累计到达，不改变漏斗的共同口径。"""
    if field not in {"sector", "lead_economy"}:
        raise ValueError("只允许按 sector 或 lead_economy 拆分")
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in observations:
        by_project[event["project_id"]].append(event)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for project in projects:
        groups[project[field]].append(project)
    result = []
    for key, group in sorted(groups.items()):
        ids = {item["id"] for item in group}
        relevant = [event for project_id in ids for event in by_project.get(project_id, [])]
        funnel = build_funnel(group, relevant)
        result.append({"key": key, "project_count": len(group),
                       "stages": funnel["stages"], "data_note": funnel["data_note"]})
    return result
