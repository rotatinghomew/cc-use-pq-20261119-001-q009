"""使用本地合成数据验证服务的核心业务链。"""

import json
import tempfile
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from bridgeboard.api.app import create_app
from bridgeboard.portfolio.database import Database


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="bridgeboard-") as folder:
        app = create_app(Database(Path(folder) / "acceptance.sqlite3"))
        with TestClient(app) as client:
            projects = [
                {"title": "菲律宾园区智能设备适配", "lead_economy": "China",
                 "partner_economies": ["Philippines"], "sector": "advanced_manufacturing",
                 "coordinator": "南向协作组", "source_ref": "synthetic:ph-01",
                 "opened_on": "2026-02-01"},
                {"title": "中新绿色能源试点", "lead_economy": "New Zealand",
                 "partner_economies": ["China"], "sector": "green_energy",
                 "coordinator": "绿色合作组", "source_ref": "synthetic:nz-01",
                 "opened_on": "2026-03-12"},
            ]
            ids = []
            for project in projects:
                response = client.post("/projects", json=project)
                response.raise_for_status()
                ids.append(response.json()["id"])
            events = [
                {"project_id": ids[0], "source_record_id": "case-ph-01",
                 "revision": 1, "kind": "partner_matched",
                 "occurred_at": "2026-02-15T09:00:00+08:00",
                 "payload": {"partner_refs": ["PH-INDUSTRIAL-PARK"],
                             "match_basis": "本地合成演练数据"}},
                {"project_id": ids[0], "source_record_id": "case-ph-02",
                 "revision": 1, "kind": "feasibility_started",
                 "occurred_at": "2026-03-01T09:00:00+08:00",
                 "payload": {"workstreams": ["设备认证", "售后网络"],
                             "readiness": "preparing"}},
                {"project_id": ids[1], "source_record_id": "case-nz-01",
                 "revision": 1, "kind": "partner_matched",
                 "occurred_at": "2026-03-20T09:00:00+08:00",
                 "payload": {"partner_refs": ["CN-ENERGY-LAB"]}},
            ]
            imported = client.post("/imports/events", json={
                "source_system": "synthetic-coordination", "records": events,
            })
            imported.raise_for_status()
            report = client.get("/analytics/portfolio", params={"as_of": date(2026, 7, 1)})
            report.raise_for_status()
            result = report.json()
            assert result["portfolio"]["project_count"] == 2
            assert result["portfolio"]["stage_counts"]["feasibility"] == 1
            assert result["aging"]["stale_project_count"] == 2
            print(json.dumps({
                "projects": result["portfolio"]["project_count"],
                "stale_projects": result["aging"]["stale_project_count"],
                "stages": result["portfolio"]["stage_counts"],
                "interpretation": result["interpretation"],
            }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
