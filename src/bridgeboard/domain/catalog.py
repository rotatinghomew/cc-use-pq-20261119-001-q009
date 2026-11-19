"""面向来源系统的受控数据目录。"""

from bridgeboard.domain.model import ECONOMIES, SECTORS, EventKind, Stage
from bridgeboard.domain.transitions import ALLOWED
from bridgeboard.intake.normalization import ALLOWED_PAYLOAD_FIELDS, REQUIRED_PAYLOAD_FIELDS


STAGE_DESCRIPTIONS = {
    Stage.DISCOVERY: "已登记合作线索，尚未确认伙伴匹配。",
    Stage.MATCHED: "已识别合作伙伴并记录匹配依据。",
    Stage.FEASIBILITY: "正在评估合作条件、工作流和准备程度。",
    Stage.AGREEMENT: "已进入协议签署后的执行准备阶段。",
    Stage.IMPLEMENTATION: "合作已开始落地或试点。",
    Stage.COMPLETED: "已有可回查证据支持的成果。",
    Stage.PAUSED: "合作暂缓，等待后续恢复或停止。",
    Stage.CLOSED: "合作已停止推进，不等同于已核实成果。",
}
EVENT_DESCRIPTIONS = {
    EventKind.INTRODUCED: "登记合作线索。",
    EventKind.PARTNER_MATCHED: "确认项目已匹配合作伙伴。",
    EventKind.FEASIBILITY_STARTED: "开始可行性评估。",
    EventKind.AGREEMENT_SIGNED: "合作协议已签署。",
    EventKind.IMPLEMENTATION_STARTED: "试点或实施工作已开始。",
    EventKind.OUTCOME_VERIFIED: "成果已通过可引用证据核实。",
    EventKind.PAUSED: "项目进入暂停状态。",
    EventKind.RESUMED: "暂停项目恢复实施。",
    EventKind.CLOSED: "项目停止推进。",
}
SECTOR_DESCRIPTIONS = {
    "advanced_manufacturing": "先进制造、产业设备与供应链协作。",
    "agriculture": "农产品、农业技术与食品产业合作。",
    "digital": "数字服务、人工智能与跨境数字业务。",
    "health": "医疗服务、生物医药与健康产业合作。",
    "logistics": "物流、仓储与跨境运输协同。",
    "trade": "商品、渠道及其他贸易合作。",
    "green_energy": "可再生能源、低碳改造与循环利用。",
    "other": "暂不适合归入其他行业的合作项目。",
}


def build_catalog() -> dict:
    return {
        "catalog_version": "1",
        "event_identity": ["source_system", "source_record_id", "revision"],
        "revision_rule": "同一来源记录的修订号从 1 开始连续递增。",
        "time_contract": "事件时间和接收时间均为带时区的 ISO 8601 时间。",
        "economies": sorted(ECONOMIES),
        "sectors": [{"code": sector, "description": SECTOR_DESCRIPTIONS[sector]}
                    for sector in sorted(SECTORS)],
        "stages": [{"code": stage.value, "description": STAGE_DESCRIPTIONS[stage]}
                   for stage in Stage],
        "events": [{
            "code": kind.value, "description": EVENT_DESCRIPTIONS[kind],
            "allowed_payload_fields": sorted(ALLOWED_PAYLOAD_FIELDS[kind]),
            "required_payload_fields": sorted(REQUIRED_PAYLOAD_FIELDS.get(kind, set())),
            "allowed_from_stages": sorted(
                stage.value if stage else "empty" for stage, kinds in ALLOWED.items()
                if kind in kinds
            ),
            "resulting_stage": _resulting_stage(kind),
        } for kind in EventKind],
    }


def _resulting_stage(kind: EventKind) -> str:
    from bridgeboard.domain.model import EVENT_STAGE
    return EVENT_STAGE[kind].value
