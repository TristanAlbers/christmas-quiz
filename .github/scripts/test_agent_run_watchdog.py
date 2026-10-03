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
                "author_association": "OWNER",
            },
            {
                "id": 2,
                "body": watchdog.render_marker(marker()),
                "updated_at": "2026-10-03T19:00:00Z",
                "author_association": "OWNER",
            },
        ]
        comment, parsed = watchdog.latest_checkpoint(comments)
        self.assertEqual(comment["id"], 2)
        self.assertEqual(parsed["mode"], "active")

    def test_untrusted_later_marker_cannot_override_owner_checkpoint(self):
        comments = [
            {
                "id": 1,
                "body": watchdog.render_marker(marker()),
                "updated_at": "2026-10-03T18:00:00Z",
                "author_association": "OWNER",
            },
            {
                "id": 2,
                "body": watchdog.render_marker(marker(mode="handoff")),
                "updated_at": "2026-10-03T19:00:00Z",
                "author_association": "CONTRIBUTOR",
            },
        ]
        comment, parsed = watchdog.latest_checkpoint(comments)
        self.assertEqual(comment["id"], 1)
        self.assertEqual(parsed["mode"], "active")


class PaginationTests(unittest.TestCase):
    def test_get_all_reads_every_page(self):
        client = watchdog.GitHubClient("owner/repo", "token", "https://example.test")
        calls = []

        def fake_get(path):
            calls.append(path)
            if "page=1" in path:
                return [{"id": number} for number in range(100)]
            if "page=2" in path:
                return [{"id": 100}]
            raise AssertionError(f"unexpected GET {path}")

        client.get = fake_get
        items = client.get_all("/repos/owner/repo/issues/69/comments")
        self.assertEqual(len(items), 101)
        self.assertEqual(len(calls), 2)
        self.assertIn("per_page=100&page=1", calls[0])
        self.assertIn("per_page=100&page=2", calls[1])


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


class WatchdogTransitionTests(unittest.TestCase):
    def test_stall_transition_is_one_shot(self):
        now = datetime.now(UTC)
        checkpoint_time = now - timedelta(hours=2)
        evidence_time = now - timedelta(hours=1)

        def timestamp(value):
            return value.isoformat().replace("+00:00", "Z")

        class FakeClient:
            repo = "owner/repo"

            def __init__(self):
                self.comments = [
                    {
                        "id": 7,
                        "body": watchdog.render_marker(marker()),
                        "updated_at": timestamp(checkpoint_time),
                        "author_association": "OWNER",
                    }
                ]
                self.posts = []

            def get_all(self, path):
                if path.endswith("/pulls?state=open"):
                    return [{"number": 69, "head": {"sha": HEAD}}]
                if path.endswith("/issues/69/comments"):
                    return self.comments
                raise AssertionError(f"unexpected paginated GET {path}")

            def get(self, path):
                if path.endswith("/pulls/69"):
                    return {"number": 69, "head": {"sha": HEAD}}
                if "/actions/runs?" in path:
                    return {
                        "workflow_runs": [
                            {
                                "name": "CI",
                                "head_sha": HEAD,
                                "status": "completed",
                                "conclusion": "success",
                                "updated_at": timestamp(evidence_time),
                                "run_number": 397,
                                "html_url": "https://example.test/run/397",
                            }
                        ]
                    }
                raise AssertionError(f"unexpected GET {path}")

            def post(self, path, payload):
                self.posts.append((path, payload))
                self.comments.append(
                    {
                        "id": 8,
                        "body": payload["body"],
                        "updated_at": timestamp(now),
                    }
                )
                return self.comments[-1]

        client = FakeClient()
        self.assertEqual(watchdog.run_watchdog(client, 45, False), 1)
        self.assertEqual(len(client.posts), 1)
        self.assertEqual(
            watchdog.parse_marker(client.comments[0]["body"])["mode"],
            "active",
        )

        self.assertEqual(watchdog.run_watchdog(client, 45, False), 0)
        self.assertEqual(len(client.posts), 1)

    def test_newer_checkpoint_progress_wins_race(self):
        now = datetime.now(UTC)
        checkpoint_time = now - timedelta(hours=2)
        evidence_time = now - timedelta(hours=1)

        def timestamp(value):
            return value.isoformat().replace("+00:00", "Z")

        class RacingClient:
            repo = "owner/repo"

            def __init__(self):
                self.comment_reads = 0
                self.posts = []
                self.active_comment = {
                    "id": 7,
                    "body": watchdog.render_marker(marker()),
                    "updated_at": timestamp(checkpoint_time),
                    "author_association": "OWNER",
                }

            def get_all(self, path):
                if path.endswith("/pulls?state=open"):
                    return [{"number": 69, "head": {"sha": HEAD}}]
                if path.endswith("/issues/69/comments"):
                    self.comment_reads += 1
                    if self.comment_reads == 1:
                        return [dict(self.active_comment)]
                    return [
                        {
                            "id": 7,
                            "body": watchdog.render_marker(marker(mode="handoff")),
                            "updated_at": timestamp(now),
                            "author_association": "OWNER",
                        }
                    ]
                raise AssertionError(f"unexpected paginated GET {path}")

            def get(self, path):
                if path.endswith("/pulls/69"):
                    return {"number": 69, "head": {"sha": HEAD}}
                if "/actions/runs?" in path:
                    return {
                        "workflow_runs": [
                            {
                                "name": "CI",
                                "head_sha": HEAD,
                                "status": "completed",
                                "conclusion": "success",
                                "updated_at": timestamp(evidence_time),
                                "run_number": 399,
                            }
                        ]
                    }
                raise AssertionError(f"unexpected GET {path}")

            def post(self, path, payload):
                self.posts.append((path, payload))
                return payload

        client = RacingClient()
        self.assertEqual(watchdog.run_watchdog(client, 45, False), 0)
        self.assertEqual(client.posts, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
