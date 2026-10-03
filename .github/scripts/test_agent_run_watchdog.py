#!/usr/bin/env python3
"""Deterministic tests for the autonomous PR run-health watchdog."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_run_watchdog as watchdog  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 10, 3, 20, 0, tzinfo=UTC)
HEAD = "a" * 40


def marker(mode="active", expected="ci", head_sha=HEAD):
    return {
        "mode": mode,
        "phase": "ci-repair",
        "expected": expected,
        "head_sha": head_sha,
    }


class MarkerTests(unittest.TestCase):
    def test_marker_round_trip(self):
        original = marker()
        parsed = watchdog.parse_marker(watchdog.render_marker(original))
        self.assertEqual(parsed, original)

    def test_latest_checkpoint_uses_server_updated_time(self):
        comments = [
            {
                "id": 1,
                "body": watchdog.render_marker(marker(mode="handoff")),
                "updated_at": "2026-10-03T18:00:00Z",
            },
            {
                "id": 2,
                "body": watchdog.render_marker(marker()),
                "updated_at": "2026-10-03T19:00:00Z",
            },
        ]
        comment, parsed = watchdog.latest_checkpoint(comments)
        self.assertEqual(comment["id"], 2)
        self.assertEqual(parsed["mode"], "active")


class EvidenceTests(unittest.TestCase):
    def test_latest_ci_evidence_requires_completed_matching_ci_run(self):
        runs = [
            {
                "name": "CI",
                "head_sha": HEAD,
                "status": "in_progress",
                "updated_at": "2026-10-03T19:20:00Z",
                "run_number": 10,
            },
            {
                "name": "Other",
                "head_sha": HEAD,
                "status": "completed",
                "conclusion": "success",
                "updated_at": "2026-10-03T19:25:00Z",
                "run_number": 11,
            },
            {
                "name": "CI",
                "head_sha": HEAD,
                "status": "completed",
                "conclusion": "failure",
                "updated_at": "2026-10-03T19:30:00Z",
                "run_number": 12,
                "html_url": "https://example.test/run/12",
            },
        ]
        evidence = watchdog.latest_ci_evidence(runs, HEAD)
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.kind, "ci")
        self.assertIn("failure", evidence.summary)
        self.assertEqual(evidence.url, "https://example.test/run/12")

    def test_review_evidence_ignores_checkpoint_and_watchdog_comments(self):
        checkpoint = {
            "id": 7,
            "body": watchdog.render_marker(marker(expected="review")),
            "updated_at": "2026-10-03T19:00:00Z",
        }
        watchdog_comment = {
            "id": 8,
            "body": "<!-- agent-run-watchdog:abc -->\nresume packet",
            "updated_at": "2026-10-03T19:40:00Z",
        }
        human_comment = {
            "id": 9,
            "body": "Review complete.",
            "updated_at": "2026-10-03T19:20:00Z",
            "html_url": "https://example.test/comment/9",
        }
        evidence = watchdog.latest_review_evidence(
            [],
            [],
            [checkpoint, watchdog_comment, human_comment],
            checkpoint_id=7,
        )
        self.assertIsNotNone(evidence)
        self.assertEqual(evidence.kind, "pr-comment")
        self.assertEqual(evidence.url, "https://example.test/comment/9")


class StallDecisionTests(unittest.TestCase):
    def setUp(self):
        self.checkpoint = NOW - timedelta(hours=2)

    def evidence(self, age_minutes):
        return watchdog.Evidence(
            "ci",
            NOW - timedelta(minutes=age_minutes),
            "CI complete",
        )

    def test_pending_external_event_is_healthy(self):
        self.assertFalse(
            watchdog.should_stall(
                marker(),
                self.checkpoint,
                HEAD,
                None,
                NOW,
                timedelta(minutes=45),
            )
        )

    def test_fresh_evidence_is_healthy(self):
        self.assertFalse(
            watchdog.should_stall(
                marker(),
                self.checkpoint,
                HEAD,
                self.evidence(20),
                NOW,
                timedelta(minutes=45),
            )
        )

    def test_old_unattended_evidence_is_stalled(self):
        self.assertTrue(
            watchdog.should_stall(
                marker(),
                self.checkpoint,
                HEAD,
                self.evidence(60),
                NOW,
                timedelta(minutes=45),
            )
        )

    def test_evidence_older_than_checkpoint_is_not_new(self):
        evidence = watchdog.Evidence(
            "ci",
            self.checkpoint - timedelta(minutes=5),
            "old CI",
        )
        self.assertFalse(
            watchdog.should_stall(
                marker(),
                self.checkpoint,
                HEAD,
                evidence,
                NOW,
                timedelta(minutes=45),
            )
        )

    def test_handoff_is_never_marked_stalled(self):
        self.assertFalse(
            watchdog.should_stall(
                marker(mode="handoff"),
                self.checkpoint,
                HEAD,
                self.evidence(60),
                NOW,
                timedelta(minutes=45),
            )
        )

    def test_head_mismatch_is_not_marked_stalled(self):
        self.assertFalse(
            watchdog.should_stall(
                marker(),
                self.checkpoint,
                "b" * 40,
                self.evidence(60),
                NOW,
                timedelta(minutes=45),
            )
        )

    def test_none_expected_event_is_not_marked_stalled(self):
        self.assertFalse(
            watchdog.should_stall(
                marker(expected="none"),
                self.checkpoint,
                HEAD,
                self.evidence(60),
                NOW,
                timedelta(minutes=45),
            )
        )

    def test_stall_key_and_notification_are_stable(self):
        evidence = self.evidence(60)
        first = watchdog.stall_key(68, marker(), evidence)
        second = watchdog.stall_key(68, marker(), evidence)
        self.assertEqual(first, second)
        body = watchdog.notification_body(68, marker(), evidence, first)
        self.assertIn(f"<!-- agent-run-watchdog:{first} -->", body)
        self.assertIn("Resume packet", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
