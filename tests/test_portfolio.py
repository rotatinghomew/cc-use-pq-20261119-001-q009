import unittest

from bridgeboard.domain.errors import Conflict, InvalidInput, NotFound
from bridgeboard.portfolio.service import PortfolioService
from tests.helpers import ServiceCase


class PortfolioTests(ServiceCase, unittest.TestCase):
    def test_duplicate_source_ref_cannot_create_two_project_identities(self):
        with self.assertRaises(Conflict):
            self.portfolio.create_project({
                "title": "同一来源重复项目", "lead_economy": "China",
                "partner_economies": ["Philippines"], "sector": "digital",
                "coordinator": "演练协调组", "source_ref": "test:project:1",
                "opened_on": "2026-01-01",
            })

    def test_partner_list_is_unique_and_preserves_first_seen_order(self):
        result = self.portfolio.create_project({
            "title": "多方合作", "lead_economy": "China",
            "partner_economies": ["Japan", "Australia", "Japan"],
            "sector": "trade", "coordinator": "组二",
            "source_ref": "test:project:multi", "opened_on": "2026-01-02",
        })
        self.assertEqual(result["partner_economies"], ["Japan", "Australia"])

    def test_lead_economy_cannot_also_be_partner(self):
        values = {"title": "错误合作关系", "lead_economy": "China",
                  "partner_economies": ["China"], "sector": "digital",
                  "coordinator": "组", "source_ref": "test:bad:lead",
                  "opened_on": "2026-01-01"}
        with self.assertRaises(InvalidInput):
            self.portfolio.create_project(values)

    def test_unknown_sector_and_economy_are_rejected(self):
        values = {"title": "错误目录", "lead_economy": "Narnia",
                  "partner_economies": ["Philippines"], "sector": "digital",
                  "coordinator": "组", "source_ref": "test:bad:economy",
                  "opened_on": "2026-01-01"}
        with self.assertRaises(InvalidInput):
            self.portfolio.create_project(values)
        values["lead_economy"] = "China"
        values["sector"] = "unknown"
        with self.assertRaises(InvalidInput):
            self.portfolio.create_project(values)

    def test_project_listing_filters_sector_and_economy(self):
        values = {"title": "另一个项目", "lead_economy": "Japan",
                  "partner_economies": ["Australia"], "sector": "green_energy",
                  "coordinator": "组二", "source_ref": "test:project:two",
                  "opened_on": "2026-01-03"}
        self.portfolio.create_project(values)
        self.assertEqual(len(self.portfolio.list_projects(sector="digital")), 1)
        self.assertEqual(len(self.portfolio.list_projects(economy="Australia")), 1)
        self.assertEqual(len(self.portfolio.list_projects(sector="digital", economy="Japan")), 0)

    def test_project_creation_initializes_a_real_discovery_observation(self):
        current = self.portfolio.get_project(self.project["id"])
        self.assertEqual(current["stage"], "discovery")
        self.assertEqual(current["event_count"], 1)
        self.assertFalse(current["verified_outcome"])

    def test_project_not_found_is_explicit(self):
        with self.assertRaises(NotFound):
            self.portfolio.get_project("nonexistent")

    def test_missing_fields_and_bad_dates_are_not_silently_defaulted(self):
        with self.assertRaises(InvalidInput):
            self.portfolio.create_project({"title": "不完整"})
        values = {"title": "错误日期", "lead_economy": "China",
                  "partner_economies": ["Philippines"], "sector": "digital",
                  "coordinator": "组", "source_ref": "test:bad:date",
                  "opened_on": "tomorrow"}
        with self.assertRaises(InvalidInput):
            self.portfolio.create_project(values)

    def test_sqlite_database_survives_service_reconstruction(self):
        reconstructed = PortfolioService(self.database)
        self.assertEqual(reconstructed.get_project(self.project["id"])["title"],
                         "合成合作项目")


if __name__ == "__main__":
    unittest.main()
