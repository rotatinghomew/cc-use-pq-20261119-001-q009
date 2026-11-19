import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from bridgeboard.api.app import create_app
from bridgeboard.portfolio.database import Database


class ApiIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app = create_app(Database(Path(self.temp.name) / "api.sqlite3"))
        self.client = TestClient(app)
        response = self.client.post("/projects", json={
            "title": "中新低碳园区", "lead_economy": "China",
            "partner_economies": ["New Zealand"], "sector": "green_energy",
            "coordinator": "绿色项目组", "source_ref": "api:project:1",
            "opened_on": "2026-01-01",
        })
        self.assertEqual(response.status_code, 201)
        self.project_id = response.json()["id"]

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def post_event(self, kind, record, day, payload, revision=1):
        return self.client.post("/imports/events", json={
            "source_system": "partner-coordination", "records": [{
                "project_id": self.project_id, "source_record_id": record,
                "revision": revision, "kind": kind,
                "occurred_at": f"2026-01-{day:02}T09:00:00+00:00",
                "payload": payload,
            }],
        })

    def test_health_and_openapi_are_available(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        spec = self.client.get("/openapi.json").json()
        self.assertIn("/analytics/portfolio", spec["paths"])
        self.assertIn("/imports/events", spec["paths"])

    def test_catalog_describes_event_payload_and_stage_contracts(self):
        catalog = self.client.get("/catalog").json()
        self.assertIn("China", catalog["economies"])
        event = next(item for item in catalog["events"]
                     if item["code"] == "outcome_verified")
        self.assertEqual(event["required_payload_fields"], ["evidence_ref", "outcome_type"])
        self.assertEqual(catalog["revision_rule"], "同一来源记录的修订号从 1 开始连续递增。")

    def test_end_to_end_new_project_events_and_operational_report(self):
        self.assertEqual(self.post_event("partner_matched", "match-1", 5,
                         {"partner_refs": ["wind-lab"]}).status_code, 201)
        self.assertEqual(self.post_event("feasibility_started", "feasibility-1", 12,
                         {"workstreams": ["grid", "permits"],
                          "readiness": "preparing"}).status_code, 201)
        project = self.client.get(f"/projects/{self.project_id}").json()
        self.assertEqual(project["stage"], "feasibility")
        report = self.client.get("/analytics/portfolio", params={"as_of": "2026-05-01"}).json()
        self.assertEqual(report["portfolio"]["stage_counts"]["feasibility"], 1)
        self.assertEqual(report["aging"]["projects"][0]["id"], self.project_id)

    def test_corrected_event_changes_timeline_and_aging_together(self):
        self.post_event("partner_matched", "match-1", 20,
                        {"partner_refs": ["wind-lab"]})
        correction = self.client.post("/imports/events", json={
            "source_system": "partner-coordination", "records": [{
                "project_id": self.project_id, "source_record_id": "match-1",
                "revision": 2, "kind": "partner_matched",
                "occurred_at": "2026-01-03T09:00:00+00:00",
                "payload": {"partner_refs": ["wind-lab-corrected"]},
            }],
        })
        self.assertEqual(correction.status_code, 201)
        project = self.client.get(f"/projects/{self.project_id}").json()
        report = self.client.get("/analytics/portfolio", params={"as_of": "2026-05-01"}).json()
        self.assertEqual(project["stage_entered_at"], "2026-01-03T09:00:00+00:00")
        self.assertEqual(report["aging"]["projects"][0]["days_in_stage"], 118)
        self.assertEqual(report["projects"][0]["source_revisions"], 1)

    def test_batch_validation_failure_does_not_partially_change_report(self):
        response = self.client.post("/imports/events", json={
            "source_system": "partner-coordination", "records": [
                {"project_id": self.project_id, "source_record_id": "match-1",
                 "revision": 1, "kind": "partner_matched",
                 "occurred_at": "2026-01-05T09:00:00+00:00",
                 "payload": {"partner_refs": ["wind-lab"]}},
                {"project_id": self.project_id, "source_record_id": "agreement-1",
                 "revision": 1, "kind": "agreement_signed",
                 "occurred_at": "2026-01-06T09:00:00+00:00",
                 "payload": {"agreement_ref": "A-1"}},
            ],
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.client.get(f"/projects/{self.project_id}").json()["stage"], "discovery")

    def test_project_creation_validation_is_exposed_as_client_error(self):
        response = self.client.post("/projects", json={
            "title": "bad", "lead_economy": "China",
            "partner_economies": ["China"], "sector": "digital",
            "coordinator": "group", "source_ref": "api:bad", "opened_on": "2026-01-01",
        })
        self.assertEqual(response.status_code, 422)

    def test_report_filters_flow_from_http_to_metrics(self):
        response = self.client.get("/analytics/portfolio", params={
            "as_of": "2026-03-01", "economy": "New Zealand",
            "sector": "green_energy", "stale_after_days": 30,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["portfolio"]["project_count"], 1)
        self.assertEqual(response.json()["filters"]["stale_after_days"], 30)

    def test_invalid_analysis_filter_is_a_domain_error(self):
        response = self.client.get("/analytics/portfolio", params={"sector": "space"})
        self.assertEqual(response.status_code, 422)

    def test_batch_receipt_can_be_retrieved_for_audit(self):
        response = self.post_event("partner_matched", "match-1", 5,
                                   {"partner_refs": ["wind-lab"]})
        batch_id = response.json()["id"]
        receipt = self.client.get(f"/imports/batches/{batch_id}")
        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.json()["accepted_count"], 1)
        self.assertEqual(receipt.json()["items"][0]["disposition"], "accepted")

    def test_project_history_exposes_old_and_current_source_revisions(self):
        self.post_event("partner_matched", "match-1", 5,
                        {"partner_refs": ["wind-lab"]})
        self.client.post("/imports/events", json={
            "source_system": "partner-coordination", "records": [{
                "project_id": self.project_id, "source_record_id": "match-1",
                "revision": 2, "kind": "partner_matched",
                "occurred_at": "2026-01-04T09:00:00+00:00",
                "payload": {"partner_refs": ["wind-lab-updated"]},
            }],
        }).raise_for_status()
        history = self.client.get(f"/projects/{self.project_id}/history").json()
        revisions = [event for event in history["timeline"]
                     if event["source_record_id"] == "match-1"]
        by_revision = sorted(revisions, key=lambda event: event["revision"])
        self.assertEqual([event["current_revision"] for event in by_revision], [False, True])
        self.assertEqual(history["revision_count"], 1)
        self.assertEqual(len(history["batches"]), 2)

    def test_cohort_and_funnel_are_part_of_portfolio_analysis(self):
        self.post_event("partner_matched", "match-1", 5,
                        {"partner_refs": ["wind-lab"]})
        report = self.client.get("/analytics/portfolio", params={"as_of": "2026-04-01"}).json()
        self.assertEqual(report["funnel"]["stages"][1]["projects_reached"], 1)
        cohort = report["opening_cohorts"][0]
        self.assertEqual(cohort["opened_month"], "2026-01")
        self.assertEqual(cohort["median_days_to_match"], 4)

    def test_transition_analysis_uses_current_revisions_once(self):
        self.post_event("partner_matched", "match-1", 5,
                        {"partner_refs": ["wind-lab"]})
        report = self.client.get("/analytics/portfolio", params={"as_of": "2026-04-01"}).json()
        transitions = report["transition_analysis"]["transitions"]
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0]["from_stage"], "discovery")
        self.assertEqual(transitions[0]["to_stage"], "matched")
        self.assertEqual(transitions[0]["transition_count"], 1)

    def test_source_quality_explains_imported_revisions(self):
        self.post_event("partner_matched", "match-1", 5,
                        {"partner_refs": ["wind-lab"]})
        self.client.post("/imports/events", json={
            "source_system": "partner-coordination", "records": [{
                "project_id": self.project_id, "source_record_id": "match-1",
                "revision": 2, "kind": "partner_matched",
                "occurred_at": "2026-01-04T09:00:00+00:00",
                "payload": {"partner_refs": ["wind-lab-updated"]},
            }],
        }).raise_for_status()
        quality = self.client.get("/analytics/sources", params={"as_of": "2026-04-01"}).json()
        source = next(item for item in quality["sources"]
                      if item["source_system"] == "partner-coordination")
        self.assertEqual(quality["source_count"], 2)
        self.assertEqual(source["revised_facts"], 1)
        self.assertTrue(any(alert["kind"] == "revisions" for alert in quality["alerts"]))

    def test_unknown_project_uses_not_found_status(self):
        response = self.client.get("/projects/not-a-project")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
