"""各业务阶段之间的实际转移与终止位置。"""

from collections import defaultdict
from statistics import median
from typing import Any

from bridgeboard.domain.model import EventKind, Stage
from bridgeboard.domain.transitions import elapsed_days, timeline
from bridgeboard.portfolio.service import active_timeline


def build_transition_analysis(projects: list[dict[str, Any]],
                             observations: list[dict[str, Any]]) -> dict[str, Any]:
    by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in observations:
        by_project[event["project_id"]].append(event)
    transitions: dict[tuple[str, str], list[float]] = defaultdict(list)
    terminal: dict[str, int] = defaultdict(int)
    pauses = 0
    resumes = 0
    projects_with_transitions = 0
    for project in projects:
        events = active_timeline(by_project.get(project["id"], []))
        if not events:
            continue
        states = timeline(events)
        if len(states) > 1:
            projects_with_transitions += 1
        for index in range(len(states) - 1):
            current, following = states[index], states[index + 1]
            key = (current.stage.value, following.stage.value)
            transitions[key].append(elapsed_days(current.entered_at, following.entered_at))
        final = states[-1].stage
        if final in {Stage.CLOSED, Stage.COMPLETED} and len(states) > 1:
            terminal[states[-2].stage.value] += 1
        pauses += sum(event["kind"] == EventKind.PAUSED.value for event in events)
        resumes += sum(event["kind"] == EventKind.RESUMED.value for event in events)
    rows = []
    for (source, target), durations in sorted(transitions.items()):
        rows.append({
            "from_stage": source, "to_stage": target,
            "transition_count": len(durations),
            "median_days_in_prior_stage": round(median(durations), 2),
            "mean_days_in_prior_stage": round(sum(durations) / len(durations), 2),
        })
    return {
        "projects_with_transitions": projects_with_transitions,
        "transition_count": sum(len(values) for values in transitions.values()),
        "transitions": rows,
        "terminal_projects_by_prior_stage": dict(sorted(terminal.items())),
        "pause_events": pauses, "resume_events": resumes,
        "interpretation": [
            "转移耗时以相邻有效阶段事件的发生时间计算；同一项目的更正版本不会重复计入。",
            "终止阶段只记录其直接前一阶段，不推断关闭原因或未观测的失败。",
        ],
    }
