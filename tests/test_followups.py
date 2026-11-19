import unittest
from datetime import date

from bridgeboard.analytics.followups import build_followups


class FollowupTests(unittest.TestCase):
    def project(self, identifier):
        return {"id": identifier, "title": identifier, "coordinator": "组",
                "sector": "digital"}

    def event(self, identifier, project_id, kind, day, payload=None):
        return {"id": identifier, "project_id": project_id,
                "source_system": "source", "source_record_id": identifier,
                "revision": 1, "kind": kind,
                "occurred_at": f"2026-01-{day:02}T09:00:00+00:00",
                "payload": payload or {}}

    def test_old_discovery_case_enters_queue_only_after_stage_threshold(self):
        projects = [self.project("p1")]
        events = [self.event("intro", "p1", "introduced", 1)]
        early = build_followups(projects, events, as_of=date(2026, 1, 20))
        late = build_followups(projects, events, as_of=date(2026, 3, 1))
        self.assertEqual(early["candidate_count"], 0)
        self.assertEqual(late["candidate_count"], 1)
        self.assertEqual(late["items"][0]["reasons"][0]["kind"], "stage_aging")

    def test_blocked_feasibility_is_flagged_before_aging_threshold(self):
        projects = [self.project("p1")]
        events = [self.event("intro", "p1", "introduced", 1),
                  self.event("match", "p1", "partner_matched", 2,
                             {"partner_refs": ["partner"]}),
                  self.event("study", "p1", "feasibility_started", 3,
                             {"readiness": "blocked"})]
        result = build_followups(projects, events, as_of=date(2026, 1, 4))
        self.assertEqual(result["items"][0]["reasons"][0]["kind"], "readiness_blocked")

    def test_pause_review_only_appears_on_or_after_review_date(self):
        projects = [self.project("p1")]
        events = [self.event("intro", "p1", "introduced", 1),
                  self.event("pause", "p1", "paused", 2,
                             {"reason": "合规待确认", "review_on": "2026-02-01"})]
        before = build_followups(projects, events, as_of=date(2026, 1, 31))
        due = build_followups(projects, events, as_of=date(2026, 2, 1))
        self.assertEqual(before["candidate_count"], 0)
        self.assertEqual(due["items"][0]["reasons"][0]["kind"], "pause_review_due")

    def test_priority_is_explainable_and_stable(self):
        projects = [self.project("p2"), self.project("p1")]
        events = [self.event("intro2", "p2", "introduced", 1),
                  self.event("intro1", "p1", "introduced", 1)]
        first = build_followups(projects, events, as_of=date(2026, 3, 1))
        second = build_followups(list(reversed(projects)), list(reversed(events)),
                                 as_of=date(2026, 3, 1))
        self.assertEqual(first, second)
        self.assertEqual(first["items"][0]["project_id"], "p1")
        self.assertTrue(first["items"][0]["reasons"])

    def test_finished_projects_are_not_in_the_coordination_queue(self):
        projects = [self.project("p1")]
        events = [self.event("intro", "p1", "introduced", 1),
                  self.event("close", "p1", "closed", 2, {"reason": "已终止"})]
        result = build_followups(projects, events, as_of=date(2026, 10, 1))
        self.assertEqual(result["items"], [])


if __name__ == "__main__":
    unittest.main()
