import unittest

from bridgeboard.domain.errors import BatchRejected, Conflict
from bridgeboard.intake.service import IntakeService
from tests.helpers import ServiceCase


class IntakeTests(ServiceCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.intake = IntakeService(self.database)

    def test_import_advances_project_and_reports_batch_receipt(self):
        record = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                            payload={"partner_refs": ["counterpart-1"]})
        batch = self.intake.import_events("coordination-desk", [record])
        self.assertEqual(batch["accepted_count"], 1)
        self.assertEqual(batch["items"][0]["disposition"], "accepted")
        self.assertEqual(self.portfolio.get_project(self.project["id"])["stage"], "matched")

    def test_identical_batch_is_idempotent(self):
        record = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                            payload={"partner_refs": ["counterpart-1"]})
        first = self.intake.import_events("coordination-desk", [record])
        second = self.intake.import_events("coordination-desk", [record])
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["accepted_count"], 1)

    def test_same_source_version_with_changed_payload_is_rejected(self):
        first = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                           payload={"partner_refs": ["counterpart-1"]})
        self.intake.import_events("coordination-desk", [first])
        changed = {**first, "payload": {"partner_refs": ["counterpart-2"]}}
        with self.assertRaises(BatchRejected):
            self.intake.import_events("coordination-desk", [changed])

    def test_next_revision_supersedes_old_timeline_fact(self):
        original = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                              payload={"partner_refs": ["counterpart-1"]})
        self.intake.import_events("coordination-desk", [original])
        corrected = {**original, "revision": 2,
                     "occurred_at": "2026-01-02T09:00:00+00:00",
                     "payload": {"partner_refs": ["counterpart-corrected"]}}
        result = self.intake.import_events("coordination-desk", [corrected])
        self.assertEqual(result["accepted_count"], 1)
        project = self.portfolio.get_project(self.project["id"])
        self.assertEqual(project["stage"], "matched")
        self.assertEqual(project["event_count"], 2)

    def test_revisions_must_be_contiguous(self):
        record = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                            revision=3, payload={"partner_refs": ["counterpart-1"]})
        with self.assertRaises(BatchRejected) as caught:
            self.intake.import_events("coordination-desk", [record])
        self.assertIn("应连续递增至 1", caught.exception.issues[0]["reason"])

    def test_batch_is_atomic_when_one_event_is_invalid(self):
        valid = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                           payload={"partner_refs": ["counterpart-1"]})
        invalid = self.event("agreement_signed", "source-2", "2026-01-06T09:00:00+00:00",
                             payload={"agreement_ref": "A-1"})
        with self.assertRaises(BatchRejected):
            self.intake.import_events("coordination-desk", [valid, invalid])
        self.assertEqual(self.portfolio.get_project(self.project["id"])["stage"], "discovery")

    def test_illegal_stage_transition_rejects_every_record(self):
        invalid = self.event("agreement_signed", "source-1", "2026-01-05T09:00:00+00:00",
                             payload={"agreement_ref": "A-1"})
        with self.assertRaises(BatchRejected):
            self.intake.import_events("coordination-desk", [invalid])
        self.assertEqual(self.portfolio.get_project(self.project["id"])["event_count"], 1)

    def test_unknown_project_rejects_batch(self):
        invalid = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                             payload={"partner_refs": ["p"]})
        invalid["project_id"] = "missing-project"
        with self.assertRaises(BatchRejected):
            self.intake.import_events("coordination-desk", [invalid])

    def test_duplicate_rows_in_one_batch_are_recorded_once(self):
        record = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                            payload={"partner_refs": ["p"]})
        batch = self.intake.import_events("coordination-desk", [record, record])
        self.assertEqual(batch["accepted_count"], 1)
        self.assertEqual(batch["duplicate_count"], 1)
        self.assertEqual(len(batch["items"]), 2)

    def test_conflicting_duplicate_rows_reject_the_batch(self):
        first = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                           payload={"partner_refs": ["p1"]})
        second = {**first, "payload": {"partner_refs": ["p2"]}}
        with self.assertRaises(BatchRejected):
            self.intake.import_events("coordination-desk", [first, second])

    def test_source_record_cannot_move_between_projects(self):
        other = self.portfolio.create_project({
            "title": "另一个项目", "lead_economy": "China",
            "partner_economies": ["Japan"], "sector": "trade",
            "coordinator": "组二", "source_ref": "test:project:2",
            "opened_on": "2026-01-01",
        })
        original = self.event("partner_matched", "source-1", "2026-01-05T09:00:00+00:00",
                              payload={"partner_refs": ["p"]})
        self.intake.import_events("coordination-desk", [original])
        moved = {**original, "project_id": other["id"], "revision": 2}
        with self.assertRaises(BatchRejected):
            self.intake.import_events("coordination-desk", [moved])

    def test_batch_size_limit_is_enforced(self):
        with self.assertRaises(Conflict):
            self.intake.import_events("coordination-desk", [{}] * 501)

    def test_empty_batch_is_not_a_successful_noop(self):
        with self.assertRaises(Conflict):
            self.intake.import_events("coordination-desk", [])


if __name__ == "__main__":
    unittest.main()
