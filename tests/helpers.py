from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from bridgeboard.portfolio.database import Database
from bridgeboard.portfolio.service import PortfolioService


class ServiceCase:
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "test.sqlite3")
        self.database.initialize()
        self.portfolio = PortfolioService(self.database)
        self.project = self.portfolio.create_project({
            "title": "合成合作项目", "lead_economy": "China",
            "partner_economies": ["Philippines"], "sector": "digital",
            "coordinator": "演练协调组", "source_ref": "test:project:1",
            "opened_on": "2026-01-01",
        })

    def tearDown(self):
        self.temp.cleanup()

    def event(self, kind, record, occurred, revision=1, payload=None):
        return {
            "project_id": self.project["id"], "source_record_id": record,
            "revision": revision, "kind": kind, "occurred_at": occurred,
            "payload": payload or {},
        }

    @staticmethod
    def timestamp(day, hour=9):
        return datetime(2026, 1, day, hour, tzinfo=timezone.utc).isoformat()
