import unittest
from datetime import date

from bridgeboard.analytics.report import build_report
from bridgeboard.analytics.service import AnalyticsService
from bridgeboard.domain.errors import InvalidInput
from bridgeboard.intake.service import IntakeService
from tests.helpers import ServiceCase


class AnalyticsTests(ServiceCase, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.intake = IntakeService(self.database)

    def add_event(self, kind, source_ref, day, payload):
        event = self.event(kind, source_ref, f"2026-01-{day:02}T09:00:00+00:00",
                           payload=payload)
        return self.intake.import_events("coordination", [event])

    def test_stage_counts_and_stale_exposure_use_current_state(self):
        self.add_event("partner_matched", "match", 10,
                       {"partner_refs": ["partner-1"]})
        report = AnalyticsService(self.database).report(as_of=date(2026, 5, 1))
        self.assertEqual(report["portfolio"]["project_count"], 1)
        self.assertEqual(report["portfolio"]["stage_counts"]["matched"], 1)
        self.assertEqual(report["aging"]["stale_project_count"], 1)
        self.assertEqual(report["projects"][0]["days_in_stage"], 111)

    def test_unfinished_projects_are_not_counted_as_failed_outcomes(self):
        report = AnalyticsService(self.database).report(as_of=date(2026, 5, 1))
        self.assertEqual(report["portfolio"]["verified_outcome_rate_of_closed"], None)
        self.assertIn("未结束项目不计作失败", report["portfolio"]["outcome_rate_note"])
        self.assertTrue(any(note["kind"] == "no_verified_outcomes"
                            for note in report["interpretation"]))

    def test_report_is_repeatable_for_the_same_business_date(self):
        service = AnalyticsService(self.database)
        first = service.report(as_of=date(2026, 4, 1))
        second = service.report(as_of=date(2026, 4, 1))
        self.assertEqual(first, second)

    def test_economy_filter_includes_either_side_of_cooperation(self):
        report = AnalyticsService(self.database).report(
            as_of=date(2026, 4, 1), economy="Philippines")
        self.assertEqual(report["portfolio"]["project_count"], 1)
        other = AnalyticsService(self.database).report(
            as_of=date(2026, 4, 1), economy="Japan")
        self.assertEqual(other["portfolio"]["project_count"], 0)

    def test_stage_duration_requires_a_completed_stage_interval(self):
        self.add_event("partner_matched", "match", 3,
                       {"partner_refs": ["partner-1"]})
        self.add_event("feasibility_started", "feasibility", 8,
                       {"workstreams": ["compliance"], "readiness": "preparing"})
        report = AnalyticsService(self.database).report(as_of=date(2026, 4, 1))
        durations = {item["stage"]: item for item in report["stage_durations"]}
        self.assertEqual(durations["discovery"]["mean_days"], 2.38)
        self.assertEqual(durations["matched"]["mean_days"], 5)
        self.assertNotIn("feasibility", durations)

    def test_paused_time_is_not_reported_as_active_stage_time(self):
        self.add_event("partner_matched", "match", 3,
                       {"partner_refs": ["partner-1"]})
        self.add_event("paused", "paused", 8, {"reason": "等待合规确认"})
        report = AnalyticsService(self.database).report(as_of=date(2026, 4, 1))
        self.assertEqual(report["projects"][0]["stage"], "paused")
        self.assertNotIn("paused", {item["stage"] for item in report["stage_durations"]})

    def test_verified_rate_uses_closed_projects_as_denominator(self):
        self.add_event("partner_matched", "match", 3,
                       {"partner_refs": ["partner-1"]})
        self.add_event("feasibility_started", "feasibility", 4,
                       {"workstreams": ["compliance"], "readiness": "ready"})
        self.add_event("agreement_signed", "agreement", 5,
                       {"agreement_ref": "AG-1"})
        self.add_event("implementation_started", "implementation", 6,
                       {"site_ref": "site-1", "investment_band": "under_1m"})
        self.add_event("outcome_verified", "outcome", 7,
                       {"outcome_type": "pilot", "evidence_ref": "evidence-1"})
        report = AnalyticsService(self.database).report(as_of=date(2026, 4, 1))
        self.assertEqual(report["portfolio"]["verified_outcome_rate_of_closed"], 1.0)

    def test_unverified_closure_contributes_zero_without_erasing_denominator(self):
        self.add_event("closed", "close", 3, {"reason": "项目不再推进"})
        report = AnalyticsService(self.database).report(as_of=date(2026, 4, 1))
        self.assertEqual(report["portfolio"]["closed_or_completed"], 1)
        self.assertEqual(report["portfolio"]["verified_outcomes"], 0)
        self.assertEqual(report["portfolio"]["verified_outcome_rate_of_closed"], 0)

    def test_zero_denominator_is_null_not_zero(self):
        empty = build_report([], [], as_of=date(2026, 1, 1))
        self.assertIsNone(empty["portfolio"]["verified_outcome_rate_of_closed"])
        self.assertEqual(empty["interpretation"][0]["kind"], "insufficient_data")

    def test_opened_date_window_filters_whole_project_cohort(self):
        report = AnalyticsService(self.database).report(
            as_of=date(2026, 4, 1), opened_from=date(2026, 2, 1))
        self.assertEqual(report["portfolio"]["project_count"], 0)

    def test_invalid_filter_period_and_staleness_window_rejected(self):
        with self.assertRaises(InvalidInput):
            build_report([], [], as_of=date(2026, 1, 1),
                         opened_from=date(2026, 2, 1), opened_to=date(2026, 1, 1))
        with self.assertRaises(InvalidInput):
            AnalyticsService(self.database).report(as_of=date(2026, 1, 1),
                                                  stale_after_days=0)

    def test_small_cohort_is_flagged_before_overinterpreting_sector_results(self):
        report = AnalyticsService(self.database).report(as_of=date(2026, 4, 1))
        self.assertTrue(any(note["kind"] == "small_cohort"
                            for note in report["interpretation"]))


if __name__ == "__main__":
    unittest.main()
