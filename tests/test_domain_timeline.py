import unittest
from datetime import datetime, timezone

from bridgeboard.domain.errors import Conflict, InvalidInput
from bridgeboard.domain.model import EventKind, parse_timestamp
from bridgeboard.domain.transitions import elapsed_days, timeline, validate_append


def make_event(kind, day, event_id=None):
    return {"id": event_id or kind, "kind": kind,
            "occurred_at": f"2026-01-{day:02}T09:00:00+00:00",
            "source_system": "test", "source_record_id": kind, "revision": 1}


class TimelineTests(unittest.TestCase):
    def test_full_happy_path_advances_each_stage(self):
        events = [make_event(kind, day) for kind, day in [
            ("introduced", 1), ("partner_matched", 2),
            ("feasibility_started", 3), ("agreement_signed", 4),
            ("implementation_started", 5), ("outcome_verified", 6),
        ]]
        result = timeline(events)
        self.assertEqual([state.stage.value for state in result], [
            "discovery", "matched", "feasibility", "agreement",
            "implementation", "completed",
        ])
        self.assertTrue(result[-1].verified_outcome)

    def test_pause_and_resume_preserve_intermediate_history(self):
        events = [make_event(kind, day) for kind, day in [
            ("introduced", 1), ("partner_matched", 2),
            ("paused", 3), ("resumed", 4),
        ]]
        result = timeline(events)
        self.assertEqual(result[-2].stage.value, "paused")
        self.assertEqual(result[-1].stage.value, "matched")
        self.assertEqual(len(result), 4)

    def test_resume_restores_the_stage_that_was_paused(self):
        events = [make_event(kind, day) for kind, day in [
            ("introduced", 1), ("partner_matched", 2),
            ("feasibility_started", 3), ("paused", 4), ("resumed", 5),
        ]]
        result = timeline(events)
        self.assertEqual(result[-2].stage.value, "paused")
        self.assertEqual(result[-1].stage.value, "feasibility")

    def test_terminal_stages_reject_later_activity(self):
        events = [make_event("introduced", 1), make_event("closed", 2),
                  make_event("resumed", 3)]
        with self.assertRaises(Conflict):
            timeline(events)

    def test_transition_requires_intermediate_agreement(self):
        with self.assertRaises(Conflict):
            timeline([make_event("introduced", 1),
                      make_event("implementation_started", 2)])

    def test_historical_insertion_is_validated_after_sorting(self):
        proposed = [make_event("feasibility_started", 3)]
        existing = [make_event("introduced", 1), make_event("partner_matched", 2)]
        validate_append(existing, proposed)
        with self.assertRaises(Conflict):
            validate_append(existing, [make_event("agreement_signed", 5)])

    def test_same_timestamp_uses_stable_source_order_independent_of_input_order(self):
        events = [make_event("introduced", 1, "a"),
                  make_event("partner_matched", 1, "b")]
        forward = timeline(events)
        backward = timeline(list(reversed(events)))
        self.assertEqual(forward, backward)
        self.assertEqual(forward[-1].stage.value, "matched")

    def test_timezone_is_required_and_normalized(self):
        value = parse_timestamp("2026-01-01T17:00:00+08:00", "when")
        self.assertEqual(value, datetime(2026, 1, 1, 9, tzinfo=timezone.utc))
        with self.assertRaises(InvalidInput):
            parse_timestamp("2026-01-01T09:00:00", "when")

    def test_elapsed_time_checks_negative_interval(self):
        start = datetime(2026, 1, 3, tzinfo=timezone.utc)
        end = datetime(2026, 1, 4, tzinfo=timezone.utc)
        self.assertEqual(elapsed_days(start, end), 1)
        with self.assertRaises(Conflict):
            elapsed_days(end, start)


if __name__ == "__main__":
    unittest.main()
