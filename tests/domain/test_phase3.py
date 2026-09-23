"""Focused deterministic tests for the phase 3 pure policies."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from quiz.domain.phase3 import (
    FREEZE_DURATION_MS,
    EffectTeamState,
    apply_direct_freeze,
    effective_gameplay_ms,
    freeze_remaining_ms,
    pause_gameplay_clock,
    purchase_uno_reverse,
    reconcile_freeze,
    remove_freeze,
    resolve_freeze_attack,
    resume_gameplay_clock,
)
from quiz.domain.types import DomainError

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)


def error_code(call, *args):
    try:
        call(*args)
    except DomainError as error:
        return error.code
    raise AssertionError("expected a domain rejection")


def team(**changes):
    original = EffectTeamState(activity_state="PUZZLE", points=10)
    return replace(original, **changes)


class GameplayClockTests(SimpleTestCase):
    def test_running_clock_includes_active_downtime_and_truncates_milliseconds(self):
        later = NOW + timedelta(seconds=17, microseconds=999)
        self.assertEqual(effective_gameplay_ms(1_200, NOW, later), 18_200)

    def test_stopped_clock_preserves_accumulated_time_across_downtime(self):
        self.assertEqual(
            effective_gameplay_ms(41_000, None, NOW + timedelta(days=2)), 41_000
        )

    def test_backward_wall_clock_is_clamped(self):
        self.assertEqual(
            effective_gameplay_ms(41_000, NOW, NOW - timedelta(hours=1)), 41_000
        )

    def test_pause_reconciles_and_resume_preserves_accumulated_time(self):
        paused = pause_gameplay_clock(
            "ADVENT_QUIZ", 10_000, NOW, NOW + timedelta(seconds=7)
        )
        self.assertEqual(paused.global_state, "PAUSED")
        self.assertEqual(paused.clock.accumulated_ms, 17_000)
        self.assertIsNone(paused.clock.anchor)

        resumed_at = NOW + timedelta(hours=3)
        resumed = resume_gameplay_clock(
            paused.global_state,
            paused.clock.accumulated_ms,
            paused.clock.anchor,
            resumed_at,
        )
        self.assertEqual(resumed.global_state, "ADVENT_QUIZ")
        self.assertEqual(resumed.clock.accumulated_ms, 17_000)
        self.assertEqual(resumed.clock.anchor, resumed_at)

    def test_pause_preserves_freeze_remaining_time_until_resume(self):
        freeze_started_ms = 25_000
        paused = pause_gameplay_clock(
            "ADVENT_QUIZ", 20_000, NOW, NOW + timedelta(seconds=15)
        )
        before_downtime = freeze_remaining_ms(
            freeze_started_ms, paused.clock.accumulated_ms
        )
        during_downtime = effective_gameplay_ms(
            paused.clock.accumulated_ms,
            paused.clock.anchor,
            NOW + timedelta(days=2),
        )
        self.assertEqual(
            freeze_remaining_ms(freeze_started_ms, during_downtime),
            before_downtime,
        )

        resumed_at = NOW + timedelta(days=2)
        resumed = resume_gameplay_clock(
            paused.global_state,
            paused.clock.accumulated_ms,
            paused.clock.anchor,
            resumed_at,
        )
        ten_seconds_later = effective_gameplay_ms(
            resumed.clock.accumulated_ms,
            resumed.clock.anchor,
            resumed_at + timedelta(seconds=10),
        )
        self.assertEqual(
            freeze_remaining_ms(freeze_started_ms, ten_seconds_later),
            before_downtime - 10_000,
        )

    def test_clock_transitions_reject_wrong_state_or_clock_pairing(self):
        self.assertEqual(
            error_code(pause_gameplay_clock, "PAUSED", 0, NOW, NOW),
            "disallowed_state",
        )
        self.assertEqual(
            error_code(pause_gameplay_clock, "ADVENT_QUIZ", 0, None, NOW),
            "invalid_input",
        )
        self.assertEqual(
            error_code(resume_gameplay_clock, "ADVENT_QUIZ", 0, None, NOW),
            "disallowed_state",
        )
        self.assertEqual(
            error_code(resume_gameplay_clock, "PAUSED", 0, NOW, NOW),
            "invalid_input",
        )

    def test_clock_rejects_naive_or_invalid_values(self):
        naive = NOW.replace(tzinfo=None)
        for accumulated, anchor, current in (
            (-1, NOW, NOW),
            (True, NOW, NOW),
            (0, naive, NOW),
            (0, NOW, naive),
        ):
            with self.subTest(
                accumulated=accumulated, anchor=anchor, current=current
            ):
                self.assertEqual(
                    error_code(
                        effective_gameplay_ms, accumulated, anchor, current
                    ),
                    "invalid_input",
                )


class FreezeProjectionTests(SimpleTestCase):
    def test_exact_five_minute_boundary_is_expired(self):
        self.assertEqual(FREEZE_DURATION_MS, 300_000)
        self.assertEqual(freeze_remaining_ms(100, 300_099), 1)
        self.assertEqual(freeze_remaining_ms(100, 300_100), 0)
        self.assertEqual(
            reconcile_freeze("FREEZE", 100, 300_099).activity_state, "FREEZE"
        )
        expired = reconcile_freeze("FREEZE", 100, 300_100)
        self.assertEqual(expired.activity_state, "PUZZLE")
        self.assertIsNone(expired.freeze_started_ms)

    def test_absent_freeze_and_invalid_pairings(self):
        self.assertIsNone(freeze_remaining_ms(None, 2_000))
        self.assertEqual(
            reconcile_freeze("PUZZLE", None, 2_000).activity_state, "PUZZLE"
        )
        for activity, started, elapsed in (
            ("FREEZE", None, 0),
            ("PUZZLE", 0, 1),
            ("UNKNOWN", None, 0),
            ("FREEZE", -1, 0),
            ("FREEZE", 2, 1),
        ):
            with self.subTest(activity=activity, started=started, elapsed=elapsed):
                self.assertEqual(
                    error_code(reconcile_freeze, activity, started, elapsed),
                    "invalid_input",
                )


class DirectFreezeTests(SimpleTestCase):
    def test_direct_freeze_is_canonical_and_does_not_consume_reverse(self):
        decision = apply_direct_freeze(
            "ADVENT_QUIZ", team(uno_reverse_active=True), 22_000
        )
        self.assertEqual(decision.team.activity_state, "FREEZE")
        self.assertEqual(decision.team.freeze_started_ms, 22_000)
        self.assertTrue(decision.team.uno_reverse_active)

    def test_admin_can_freeze_while_paused_at_stopped_gameplay_time(self):
        decision = apply_direct_freeze("PAUSED", team(), 91_000)
        self.assertEqual(decision.team.freeze_started_ms, 91_000)

    def test_duplicate_active_freeze_and_ineligible_target_are_rejected(self):
        active = team(activity_state="FREEZE", freeze_started_ms=10)
        self.assertEqual(
            error_code(apply_direct_freeze, "ADVENT_QUIZ", active, 20),
            "already_active",
        )
        for global_state, candidate in (
            ("READY", team()),
            ("MUSIC_QUIZ", team()),
            ("FINISHED", team()),
            ("ADVENT_QUIZ", team(activity_state="FINISHED")),
            ("ADVENT_QUIZ", team(activity_state="CHALLENGE")),
        ):
            with self.subTest(global_state=global_state, candidate=candidate):
                self.assertEqual(
                    error_code(
                        apply_direct_freeze, global_state, candidate, 20
                    ),
                    "disallowed_state",
                )

    def test_expired_freeze_can_be_applied_again_at_boundary(self):
        expired = team(activity_state="FREEZE", freeze_started_ms=5)
        decision = apply_direct_freeze(
            "ADVENT_QUIZ", expired, 5 + FREEZE_DURATION_MS
        )
        self.assertEqual(decision.team.activity_state, "FREEZE")
        self.assertEqual(decision.team.freeze_started_ms, 5 + FREEZE_DURATION_MS)

    def test_remove_freeze_works_during_advent_or_pause_only(self):
        frozen = team(activity_state="FREEZE", freeze_started_ms=10)
        for global_state in ("ADVENT_QUIZ", "PAUSED"):
            with self.subTest(global_state=global_state):
                removed = remove_freeze(global_state, frozen, 20)
                self.assertEqual(removed.team.activity_state, "PUZZLE")
                self.assertIsNone(removed.team.freeze_started_ms)
        self.assertEqual(
            error_code(remove_freeze, "MUSIC_QUIZ", frozen, 20),
            "disallowed_state",
        )
        self.assertEqual(
            error_code(remove_freeze, "ADVENT_QUIZ", team(), 20),
            "disallowed_state",
        )


class FreezeAttackTests(SimpleTestCase):
    def test_attack_charges_and_freezes_target(self):
        decision = resolve_freeze_attack(
            "ADVENT_QUIZ", team(points=7), team(points=4), 123_000, 7
        )
        self.assertFalse(decision.reversed)
        self.assertEqual(decision.points_delta, -7)
        self.assertEqual(decision.attacker.points, 0)
        self.assertEqual(decision.attacker.activity_state, "PUZZLE")
        self.assertEqual(decision.target.activity_state, "FREEZE")
        self.assertEqual(decision.target.freeze_started_ms, 123_000)

    def test_reverse_is_consumed_and_attacker_is_frozen_but_still_pays(self):
        decision = resolve_freeze_attack(
            "ADVENT_QUIZ",
            team(points=12),
            team(points=4, uno_reverse_active=True),
            123_000,
            7,
        )
        self.assertTrue(decision.reversed)
        self.assertEqual(decision.attacker.points, 5)
        self.assertEqual(decision.attacker.activity_state, "FREEZE")
        self.assertEqual(decision.attacker.freeze_started_ms, 123_000)
        self.assertEqual(decision.target.activity_state, "PUZZLE")
        self.assertFalse(decision.target.uno_reverse_active)

    def test_attack_rejects_insufficient_points_without_a_partial_decision(self):
        self.assertEqual(
            error_code(
                resolve_freeze_attack,
                "ADVENT_QUIZ",
                team(points=6),
                team(uno_reverse_active=True),
                1_000,
                7,
            ),
            "insufficient_points",
        )

    def test_attack_rejects_interruptions_and_ineligible_participants(self):
        for global_state, attacker, target in (
            ("PAUSED", team(), team()),
            ("MUSIC_QUIZ", team(), team()),
            ("ADVENT_QUIZ", team(activity_state="FINISHED"), team()),
            ("ADVENT_QUIZ", team(), team(activity_state="FINISHED")),
            ("ADVENT_QUIZ", team(), team(activity_state="CHALLENGE")),
        ):
            with self.subTest(global_state=global_state):
                self.assertEqual(
                    error_code(
                        resolve_freeze_attack,
                        global_state,
                        attacker,
                        target,
                        1_000,
                        3,
                    ),
                    "disallowed_state",
                )

    def test_attack_rejects_active_target_but_accepts_exactly_expired_target(self):
        active = team(activity_state="FREEZE", freeze_started_ms=0)
        self.assertEqual(
            error_code(
                resolve_freeze_attack,
                "ADVENT_QUIZ",
                team(),
                active,
                FREEZE_DURATION_MS - 1,
                3,
            ),
            "already_active",
        )
        accepted = resolve_freeze_attack(
            "ADVENT_QUIZ",
            team(),
            active,
            FREEZE_DURATION_MS,
            3,
        )
        self.assertEqual(accepted.target.freeze_started_ms, FREEZE_DURATION_MS)

    def test_attack_rejects_negative_cost(self):
        self.assertEqual(
            error_code(
                resolve_freeze_attack,
                "ADVENT_QUIZ",
                team(),
                team(),
                0,
                -1,
            ),
            "invalid_input",
        )


class UnoReversePurchaseTests(SimpleTestCase):
    def test_purchase_charges_configured_cost_and_activates_reverse(self):
        decision = purchase_uno_reverse("ADVENT_QUIZ", team(points=7), 10, 7)
        self.assertEqual(decision.points_delta, -7)
        self.assertEqual(decision.team.points, 0)
        self.assertTrue(decision.team.uno_reverse_active)

    def test_duplicate_insufficient_and_ineligible_purchases_are_rejected(self):
        self.assertEqual(
            error_code(
                purchase_uno_reverse,
                "ADVENT_QUIZ",
                team(uno_reverse_active=True),
                0,
                3,
            ),
            "already_active",
        )
        self.assertEqual(
            error_code(
                purchase_uno_reverse, "ADVENT_QUIZ", team(points=2), 0, 3
            ),
            "insufficient_points",
        )
        for global_state, candidate in (
            ("PAUSED", team()),
            ("MUSIC_QUIZ", team()),
            ("ADVENT_QUIZ", team(activity_state="FREEZE", freeze_started_ms=0)),
            ("ADVENT_QUIZ", team(activity_state="FINISHED")),
        ):
            with self.subTest(global_state=global_state):
                self.assertEqual(
                    error_code(
                        purchase_uno_reverse,
                        global_state,
                        candidate,
                        1,
                        3,
                    ),
                    "disallowed_state",
                )
