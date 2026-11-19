import unittest
from datetime import date

from bridgeboard.analytics.cohorts import build_cohorts
from bridgeboard.analytics.funnel import build_funnel, stage_reach_by_dimension
from bridgeboard.analytics.source_quality import build_source_quality


def project(identifier, opened="2026-01-01", sector="digital", lead="China"):
    return {"id": identifier, "opened_on": opened, "sector": sector,
            "lead_economy": lead, "partner_economies": ["Philippines"]}


def event(identifier, project_id, kind, day, revision=1, received_day=None):
    return {"id": identifier, "project_id": project_id,
            "source_system": "source-a", "source_record_id": identifier,
            "revision": revision, "kind": kind,
            "occurred_at": f"2026-01-{day:02}T09:00:00+00:00",
            "received_at": f"2026-01-{received_day or day:02}T09:00:00+00:00",
            "payload": {}}


class FunnelTests(unittest.TestCase):
    def test_cumulative_reached_stages_are_not_current_stage_counts(self):
        projects = [project("p1"), project("p2")]
        events = [event("e1", "p1", "introduced", 1),
                  event("e2", "p1", "partner_matched", 2),
                  event("e3", "p1", "feasibility_started", 3),
                  event("e4", "p2", "introduced", 1)]
        result = build_funnel(projects, events)
        counts = {item["stage"]: item["projects_reached"] for item in result["stages"]}
        self.assertEqual(counts["discovery"], 2)
        self.assertEqual(counts["matched"], 1)
        self.assertEqual(counts["feasibility"], 1)
        self.assertEqual(result["stages"][2]["conversion_from_prior_stage"], 1)

    def test_empty_funnel_does_not_invent_conversion_values(self):
        result = build_funnel([], [])
        self.assertIsNone(result["stages"][0]["share_of_all_projects"])
        self.assertIsNone(result["stages"][1]["conversion_from_prior_stage"])
        self.assertTrue(result["data_note"])

    def test_paused_and_closed_projects_are_not_miscounted_as_funnel_stages(self):
        projects = [project("p1")]
        events = [event("e1", "p1", "introduced", 1),
                  event("e2", "p1", "closed", 2)]
        result = build_funnel(projects, events)
        self.assertEqual(result["closed_projects"], 1)
        self.assertEqual(result["stages"][-1]["projects_reached"], 0)

    def test_dimension_funnel_only_allows_documented_business_dimensions(self):
        projects = [project("p1", sector="digital"),
                    project("p2", sector="green_energy", lead="Japan")]
        groups = stage_reach_by_dimension(projects, [], "sector")
        self.assertEqual([group["key"] for group in groups], ["digital", "green_energy"])
        with self.assertRaises(ValueError):
            stage_reach_by_dimension(projects, [], "coordinator")

    def test_revision_replaces_old_stage_occurrence_for_funnel(self):
        projects = [project("p1")]
        events = [event("e1", "p1", "introduced", 1),
                  event("e2", "p1", "partner_matched", 20, revision=1),
                  event("e3", "p1", "partner_matched", 3, revision=2)]
        events[1]["source_record_id"] = "match"
        events[2]["source_record_id"] = "match"
        result = build_funnel(projects, events)
        self.assertEqual(result["stages"][1]["projects_reached"], 1)

    def test_resume_does_not_count_as_implementation_milestone(self):
        projects = [project("p1")]
        events = [event("e0", "p1", "introduced", 1),
                  event("e1", "p1", "partner_matched", 2),
                  event("e2", "p1", "paused", 3),
                  event("e3", "p1", "resumed", 4)]
        result = build_funnel(projects, events)
        counts = {item["stage"]: item["projects_reached"] for item in result["stages"]}
        self.assertEqual(counts["matched"], 1)
        self.assertEqual(counts["implementation"], 0)


class CohortTests(unittest.TestCase):
    def test_cohort_groups_by_project_opening_month(self):
        projects = [project("p1", "2026-01-01"), project("p2", "2026-02-01")]
        result = build_cohorts(projects, [])
        self.assertEqual([row["opened_month"] for row in result], ["2026-01", "2026-02"])
        self.assertEqual([row["project_count"] for row in result], [1, 1])

    def test_project_match_delay_is_measured_from_open_date(self):
        projects = [project("p1")]
        events = [event("e1", "p1", "introduced", 1),
                  event("e2", "p1", "partner_matched", 8)]
        result = build_cohorts(projects, events)[0]
        self.assertEqual(result["median_days_to_match"], 7)

    def test_revision_changes_cohort_matching_delay(self):
        projects = [project("p1")]
        events = [event("e1", "p1", "introduced", 1),
                  event("e2", "p1", "partner_matched", 20, revision=1),
                  event("e3", "p1", "partner_matched", 5, revision=2)]
        result = build_cohorts(projects, events)[0]
        self.assertEqual(result["median_days_to_match"], 4)

    def test_empty_or_immature_cohort_returns_explanations(self):
        result = build_cohorts([project("p1")], [])[0]
        self.assertIsNone(result["verified_outcome_rate_of_closed"])
        self.assertTrue(any("尚无关闭" in note for note in result["interpretation"]))
        self.assertTrue(any("尚无伙伴匹配" in note for note in result["interpretation"]))


class SourceQualityTests(unittest.TestCase):
    def test_source_summary_counts_duplicate_submissions_and_revisions(self):
        events = [event("e1", "p1", "introduced", 1),
                  event("e2", "p1", "partner_matched", 2, revision=2)]
        batches = [{"source_system": "source-a", "record_count": 3,
                    "accepted_count": 2, "duplicate_count": 1}]
        report = build_source_quality(events, batches, as_of=date(2026, 2, 1))
        summary = report["sources"][0]
        self.assertEqual(summary["revised_facts"], 1)
        self.assertEqual(summary["duplicate_records"], 1)
        self.assertEqual(summary["duplicate_share"], 0.3333)

    def test_arrival_delay_is_distinct_from_project_stage_duration(self):
        events = [event("late", "p1", "partner_matched", 1, received_day=20)]
        report = build_source_quality(events, [], as_of=date(2026, 2, 1))
        summary = report["sources"][0]
        self.assertEqual(summary["median_arrival_delay_days"], 19)
        self.assertEqual(summary["events_over_seven_days_late"], 1)
        self.assertEqual(report["alerts"][0]["kind"], "delayed_arrival")

    def test_empty_sources_do_not_report_zero_delay_as_measured_data(self):
        report = build_source_quality([], [], as_of=date(2026, 1, 1))
        self.assertEqual(report["source_count"], 0)
        self.assertEqual(report["event_count"], 0)
        self.assertEqual(report["sources"], [])

    def test_p90_is_bounded_by_observed_delay_values(self):
        events = [event(f"e{i}", "p1", "introduced", 1, received_day=1 + i)
                  for i in range(1, 6)]
        report = build_source_quality(events, [], as_of=date(2026, 2, 1))
        summary = report["sources"][0]
        self.assertGreaterEqual(summary["p90_arrival_delay_days"],
                                summary["median_arrival_delay_days"])
        self.assertLessEqual(summary["p90_arrival_delay_days"], 5)


if __name__ == "__main__":
    unittest.main()
