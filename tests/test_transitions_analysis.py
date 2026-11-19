import unittest

from bridgeboard.analytics.transitions import build_transition_analysis


def make_project(identifier):
    return {"id": identifier}


def make_event(identifier, project_id, source_record, kind, day, revision=1):
    return {"id": identifier, "project_id": project_id,
            "source_system": "partner-feed", "source_record_id": source_record,
            "revision": revision, "kind": kind,
            "occurred_at": f"2026-01-{day:02}T09:00:00+00:00", "payload": {}}


class TransitionAnalysisTests(unittest.TestCase):
    def test_transition_duration_uses_neighboring_business_events(self):
        projects = [make_project("p1")]
        events = [make_event("e1", "p1", "intro", "introduced", 1),
                  make_event("e2", "p1", "match", "partner_matched", 6)]
        result = build_transition_analysis(projects, events)
        self.assertEqual(result["transitions"][0]["median_days_in_prior_stage"], 5)
        self.assertEqual(result["transition_count"], 1)

    def test_correction_changes_duration_without_counting_superseded_version(self):
        projects = [make_project("p1")]
        events = [make_event("e1", "p1", "intro", "introduced", 1),
                  make_event("e2", "p1", "match", "partner_matched", 20, 1),
                  make_event("e3", "p1", "match", "partner_matched", 5, 2)]
        result = build_transition_analysis(projects, events)
        self.assertEqual(result["transition_count"], 1)
        self.assertEqual(result["transitions"][0]["median_days_in_prior_stage"], 4)

    def test_terminal_location_records_only_immediate_prior_stage(self):
        projects = [make_project("p1")]
        events = [make_event("e1", "p1", "intro", "introduced", 1),
                  make_event("e2", "p1", "match", "partner_matched", 2),
                  make_event("e3", "p1", "close", "closed", 3)]
        result = build_transition_analysis(projects, events)
        self.assertEqual(result["terminal_projects_by_prior_stage"], {"matched": 1})

    def test_pause_and_resume_are_separate_events_not_failed_transitions(self):
        projects = [make_project("p1")]
        events = [make_event("e1", "p1", "intro", "introduced", 1),
                  make_event("e2", "p1", "match", "partner_matched", 2),
                  make_event("e3", "p1", "pause", "paused", 3),
                  make_event("e4", "p1", "resume", "resumed", 5)]
        result = build_transition_analysis(projects, events)
        self.assertEqual(result["pause_events"], 1)
        self.assertEqual(result["resume_events"], 1)
        self.assertEqual(result["terminal_projects_by_prior_stage"], {})

    def test_no_data_returns_empty_transition_rows_and_definition(self):
        result = build_transition_analysis([], [])
        self.assertEqual(result["transitions"], [])
        self.assertEqual(result["transition_count"], 0)
        self.assertEqual(len(result["interpretation"]), 2)


if __name__ == "__main__":
    unittest.main()
