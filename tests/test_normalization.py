import unittest

from bridgeboard.domain.errors import InvalidInput
from bridgeboard.intake.normalization import normalize_event


def event(**changes):
    value = {"project_id": "project-1", "source_record_id": "source-1",
             "revision": 1, "kind": "partner_matched",
             "occurred_at": "2026-02-03T10:00:00+08:00",
             "payload": {"partner_refs": ["partner-1", "partner-1"]}}
    value.update(changes)
    return value


class NormalizationTests(unittest.TestCase):
    def test_normalizes_timestamps_and_deduplicates_partner_refs(self):
        result = normalize_event(event(), "source-a")
        self.assertEqual(result["occurred_at"], "2026-02-03T02:00:00+00:00")
        self.assertEqual(result["payload"]["partner_refs"], ["partner-1"])
        self.assertEqual(len(result["payload_hash"]), 64)

    def test_payload_key_order_does_not_change_hash(self):
        left = event(payload={"partner_refs": ["p"], "match_basis": "direct"})
        right = event(payload={"match_basis": "direct", "partner_refs": ["p"]})
        self.assertEqual(normalize_event(left, "source")["payload_hash"],
                         normalize_event(right, "source")["payload_hash"])

    def test_rejects_unknown_event_kind(self):
        with self.assertRaises(InvalidInput):
            normalize_event(event(kind="invented"), "source")

    def test_rejects_timestamp_without_timezone(self):
        with self.assertRaises(InvalidInput):
            normalize_event(event(occurred_at="2026-02-03T10:00:00"), "source")

    def test_rejects_nonpositive_and_boolean_revisions(self):
        for revision in (0, -1, True, 1.0):
            with self.subTest(revision=revision), self.assertRaises(InvalidInput):
                normalize_event(event(revision=revision), "source")

    def test_rejects_unrecognized_payload_fields(self):
        with self.assertRaises(InvalidInput):
            normalize_event(event(payload={"partner_refs": ["p"], "owner_id": "x"}), "source")

    def test_partner_match_requires_partner_reference(self):
        with self.assertRaises(InvalidInput):
            normalize_event(event(payload={}), "source")

    def test_business_milestones_require_analysis_context_fields(self):
        invalid = [
            event(kind="feasibility_started", payload={"readiness": "ready"}),
            event(kind="agreement_signed", payload={}),
            event(kind="implementation_started", payload={}),
        ]
        for record in invalid:
            with self.subTest(kind=record["kind"]), self.assertRaises(InvalidInput):
                normalize_event(record, "source")

    def test_verified_outcome_requires_evidence(self):
        with self.assertRaises(InvalidInput):
            normalize_event(event(kind="outcome_verified", payload={}), "source")
        result = normalize_event(event(kind="outcome_verified", payload={
            "outcome_type": "pilot", "evidence_ref": "evidence://case"}), "source")
        self.assertEqual(result["payload"]["outcome_type"], "pilot")

    def test_pause_and_close_require_reason(self):
        for kind in ("paused", "closed"):
            with self.subTest(kind=kind), self.assertRaises(InvalidInput):
                normalize_event(event(kind=kind, payload={}), "source")

    def test_rejects_control_characters_and_oversized_values(self):
        with self.assertRaises(InvalidInput):
            normalize_event(event(source_record_id="bad\nkey"), "source")
        with self.assertRaises(InvalidInput):
            normalize_event(event(payload={"partner_refs": ["x" * 161]}), "source")

    def test_canonical_json_preserves_integer_values(self):
        result = normalize_event(event(kind="implementation_started", payload={
            "investment_band": "1m_10m", "site_ref": "park-1"}), "source")
        self.assertEqual(result["payload"]["investment_band"], "1m_10m")

    def test_source_system_is_validated(self):
        with self.assertRaises(InvalidInput):
            normalize_event(event(), " ")


if __name__ == "__main__":
    unittest.main()
