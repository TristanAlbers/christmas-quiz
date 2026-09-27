"""Focused deterministic tests for phase 4 Music policies."""

from dataclasses import fields
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from quiz.domain.phase3 import GameplayClock, effective_gameplay_ms
from quiz.domain.phase4 import (
    MUSIC_GATHERING_DURATION_MS,
    MUSIC_QUESTION_TOTAL,
    MusicClock,
    MusicScore,
    UnderlyingTeamState,
    begin_music_interruption,
    effective_music_ms,
    music_phase_elapsed_ms,
    pause_music_interruption,
    reconcile_music_timing,
    resolve_music_answer,
    resume_music_interruption,
)
from quiz.domain.types import DomainError

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=UTC)


def error_code(call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except DomainError as error:
        return error.code
    raise AssertionError("expected a domain rejection")


def underlying_teams():
    return (
        UnderlyingTeamState("team-a", "PUZZLE", None),
        UnderlyingTeamState("team-b", "FREEZE", 12_345),
    )


def scores_for_question(number, a_score=None):
    resolved = number - 1
    if a_score is None:
        a_score = resolved // 2
    return (
        MusicScore("team-a", a_score),
        MusicScore("team-b", resolved - a_score),
    )


def answer_args(**changes):
    original = {
        "global_state": "MUSIC_QUIZ",
        "phase": "question",
        "current_question_id": "music-4",
        "submitted_question_id": "music-4",
        "current_question_number": 4,
        "validator_type": "text_exact",
        "expected_answer": "Fairytale of New York",
        "submitted_answer": "fairytale of new york",
        "team_id": "team-a",
        "scores": scores_for_question(4, a_score=1),
        "team_points": 17,
        "reward_points": 6,
        "current_music_ms": 45_000,
    }
    original.update(changes)
    return original


class MusicInterruptionTests(SimpleTestCase):
    def test_first_trigger_stops_advent_and_starts_separate_music_clock(self):
        teams = underlying_teams()
        decision = begin_music_interruption(
            global_state="ADVENT_QUIZ",
            already_triggered=False,
            advent_clock=GameplayClock(10_000, NOW),
            underlying_teams=teams,
            now=NOW + timedelta(seconds=7),
        )
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.global_state, "MUSIC_QUIZ")
        self.assertEqual(decision.advent_clock, GameplayClock(17_000, None))
        self.assertEqual(
            decision.music_clock,
            MusicClock(0, NOW + timedelta(seconds=7)),
        )
        self.assertIsNone(decision.pause_resume_target)
        self.assertIs(decision.underlying_teams, teams)
        self.assertEqual(decision.phase, "gathering")
        self.assertIsNone(decision.current_question_number)
        self.assertIsNone(decision.current_question_started_ms)

    def test_existing_durable_trigger_is_noop_and_does_not_restart_clocks(self):
        clock = GameplayClock(10_000, NOW)
        decision = begin_music_interruption(
            global_state="ADVENT_QUIZ",
            already_triggered=True,
            advent_clock=clock,
            underlying_teams=underlying_teams(),
            now=NOW + timedelta(days=1),
        )
        self.assertFalse(decision.triggered)
        self.assertEqual(decision.global_state, "ADVENT_QUIZ")
        self.assertIs(decision.advent_clock, clock)
        self.assertIsNone(decision.music_clock)
        self.assertIsNone(decision.phase)
        self.assertIsNone(decision.current_question_number)
        self.assertIsNone(decision.current_question_started_ms)

    def test_pause_and_resume_preserve_exact_underlying_activity_and_freeze(self):
        teams = underlying_teams()
        advent = GameplayClock(17_000, None)
        paused = pause_music_interruption(
            global_state="MUSIC_QUIZ",
            advent_clock=advent,
            music_clock=MusicClock(5_000, NOW),
            underlying_teams=teams,
            now=NOW + timedelta(seconds=8),
        )
        self.assertEqual(paused.global_state, "PAUSED")
        self.assertEqual(paused.music_clock, MusicClock(13_000, None))
        self.assertEqual(paused.pause_resume_target, "MUSIC_QUIZ")
        self.assertIs(paused.advent_clock, advent)
        self.assertIs(paused.underlying_teams, teams)

        resumed_at = NOW + timedelta(days=2)
        resumed = resume_music_interruption(
            global_state="PAUSED",
            pause_resume_target=paused.pause_resume_target,
            advent_clock=paused.advent_clock,
            music_clock=paused.music_clock,
            underlying_teams=paused.underlying_teams,
            now=resumed_at,
        )
        self.assertEqual(resumed.global_state, "MUSIC_QUIZ")
        self.assertEqual(resumed.music_clock, MusicClock(13_000, resumed_at))
        self.assertIs(resumed.advent_clock, advent)
        self.assertIs(resumed.underlying_teams, teams)

    def test_interruption_decisions_cannot_rewrite_other_advent_properties(self):
        decision = pause_music_interruption(
            global_state="MUSIC_QUIZ",
            advent_clock=GameplayClock(0, None),
            music_clock=MusicClock(0, NOW),
            underlying_teams=underlying_teams(),
            now=NOW,
        )
        names = {field.name for field in fields(type(decision))}
        self.assertNotIn("points", names)
        self.assertNotIn("inventory", names)
        self.assertNotIn("fragments", names)
        self.assertNotIn("uno_reverse_active", names)

    def test_illegal_transitions_and_clock_pairings_are_rejected(self):
        common = {
            "advent_clock": GameplayClock(0, None),
            "music_clock": MusicClock(0, NOW),
            "underlying_teams": underlying_teams(),
            "now": NOW,
        }
        self.assertEqual(
            error_code(
                pause_music_interruption,
                global_state="PAUSED",
                **common,
            ),
            "disallowed_state",
        )
        self.assertEqual(
            error_code(
                resume_music_interruption,
                global_state="PAUSED",
                pause_resume_target="ADVENT_QUIZ",
                advent_clock=GameplayClock(0, None),
                music_clock=MusicClock(0, None),
                underlying_teams=underlying_teams(),
                now=NOW,
            ),
            "disallowed_state",
        )
        self.assertEqual(
            error_code(
                pause_music_interruption,
                global_state="MUSIC_QUIZ",
                advent_clock=GameplayClock(0, NOW),
                music_clock=MusicClock(0, NOW),
                underlying_teams=underlying_teams(),
                now=NOW,
            ),
            "invalid_input",
        )


class MusicAnswerTests(SimpleTestCase):
    def test_wrong_current_answer_is_accepted_without_penalty_or_advance(self):
        original_scores = scores_for_question(4, a_score=1)
        decision = resolve_music_answer(
            **answer_args(submitted_answer="wrong", scores=original_scores)
        )
        self.assertEqual(decision.outcome, "incorrect")
        self.assertFalse(decision.advanced)
        self.assertEqual(decision.current_question_number, 4)
        self.assertIs(decision.scores, original_scores)
        self.assertEqual(decision.team_points, 17)
        self.assertEqual(decision.score_delta, 0)
        self.assertEqual(decision.points_delta, 0)
        self.assertIsNone(decision.winner_team_id)

    def test_first_correct_answer_scores_and_rewards_then_advances(self):
        decision = resolve_music_answer(**answer_args())
        self.assertEqual(decision.outcome, "won")
        self.assertTrue(decision.advanced)
        self.assertEqual(decision.phase, "question")
        self.assertEqual(decision.attempted_question_number, 4)
        self.assertEqual(decision.current_question_number, 5)
        self.assertEqual(decision.scores[0], MusicScore("team-a", 2))
        self.assertEqual(decision.scores[1], MusicScore("team-b", 2))
        self.assertEqual(decision.team_points, 23)
        self.assertEqual(decision.score_delta, 1)
        self.assertEqual(decision.points_delta, 6)
        self.assertEqual(decision.winner_team_id, "team-a")
        self.assertIsNone(decision.final_results_started_ms)

    def test_questions_two_through_ten_still_advance_immediately(self):
        for number in range(2, MUSIC_QUESTION_TOTAL):
            with self.subTest(number=number):
                decision = resolve_music_answer(
                    **answer_args(
                        current_question_id=f"music-{number}",
                        submitted_question_id=f"music-{number}",
                        current_question_number=number,
                        scores=scores_for_question(number),
                    )
                )
                self.assertEqual(decision.phase, "question")
                self.assertEqual(decision.current_question_number, number + 1)
                self.assertIsNone(decision.final_results_started_ms)

    def test_question_eleven_enters_final_results_at_current_music_time(self):
        decision = resolve_music_answer(
            **answer_args(
                current_question_id="music-11",
                submitted_question_id="music-11",
                current_question_number=11,
                scores=scores_for_question(11, a_score=6),
                team_id="team-b",
                current_music_ms=98_765,
            )
        )
        self.assertEqual(decision.phase, "final_results")
        self.assertIsNone(decision.current_question_number)
        self.assertEqual(decision.final_results_started_ms, 98_765)
        self.assertEqual(sum(item.score for item in decision.scores), 11)

    def test_stale_id_wins_no_attempt_score_reward_or_advance_decision(self):
        self.assertEqual(
            error_code(
                resolve_music_answer,
                **answer_args(submitted_question_id="music-3"),
            ),
            "stale_question",
        )

    def test_pause_final_results_and_advent_all_reject_as_disallowed(self):
        for global_state, phase, question_id in (
            ("PAUSED", "question", "music-4"),
            ("MUSIC_QUIZ", "final_results", None),
            ("ADVENT_QUIZ", "completed", None),
        ):
            with self.subTest(global_state=global_state, phase=phase):
                self.assertEqual(
                    error_code(
                        resolve_music_answer,
                        **answer_args(
                            global_state=global_state,
                            phase=phase,
                            current_question_id=question_id,
                        ),
                    ),
                    "disallowed_state",
                )

    def test_gathering_rejects_before_staleness_without_a_decision(self):
        for current_question_id, submitted_question_id in (
            (None, "music-1"),
            ("music-1", "stale-music-question"),
        ):
            with self.subTest(current_question_id=current_question_id):
                self.assertEqual(
                    error_code(
                        resolve_music_answer,
                        **answer_args(
                            phase="gathering",
                            current_question_id=current_question_id,
                            submitted_question_id=submitted_question_id,
                        ),
                    ),
                    "disallowed_state",
                )

    def test_delayed_previous_id_is_stale_after_immediate_advance(self):
        next_scores = (MusicScore("team-a", 2), MusicScore("team-b", 2))
        self.assertEqual(
            error_code(
                resolve_music_answer,
                **answer_args(
                    current_question_id="music-5",
                    submitted_question_id="music-4",
                    current_question_number=5,
                    scores=next_scores,
                ),
            ),
            "stale_question",
        )

    def test_invalid_score_or_reward_inputs_are_rejected(self):
        for changes in (
            {"scores": (MusicScore("team-a", 0), MusicScore("team-b", 0))},
            {"reward_points": -1},
            {"team_points": -1},
            {"team_id": "unknown"},
            {"submitted_answer": "   "},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    error_code(resolve_music_answer, **answer_args(**changes)),
                    "invalid_input",
                )


class MusicTimingTests(SimpleTestCase):
    def test_music_clock_is_independent_and_active_downtime_counts(self):
        self.assertEqual(
            effective_music_ms(3_000, NOW, NOW + timedelta(days=1, seconds=2)),
            86_405_000,
        )
        self.assertEqual(
            effective_music_ms(3_000, None, NOW + timedelta(days=4)), 3_000
        )

    def test_gathering_has_one_millisecond_remaining_before_boundary(self):
        decision = reconcile_music_timing(
            global_state="MUSIC_QUIZ",
            pause_resume_target=None,
            phase="gathering",
            music_clock=MusicClock(0, NOW),
            advent_clock=GameplayClock(44_000, None),
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=None,
            final_results_duration_ms=60_000,
            now=NOW + timedelta(milliseconds=59_999),
        )
        self.assertEqual(decision.phase, "gathering")
        self.assertEqual(decision.gathering_remaining_ms, 1)
        self.assertIsNone(decision.current_question_number)
        self.assertIsNone(decision.current_question_started_ms)
        self.assertIsNone(decision.logical_transition_at)

    def test_gathering_boundary_starts_question_one_at_fixed_music_marker(self):
        decision = reconcile_music_timing(
            global_state="MUSIC_QUIZ",
            pause_resume_target=None,
            phase="gathering",
            music_clock=MusicClock(0, NOW),
            advent_clock=GameplayClock(44_000, None),
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=None,
            final_results_duration_ms=60_000,
            now=NOW + timedelta(seconds=60),
        )
        self.assertEqual(decision.phase, "question")
        self.assertEqual(decision.current_question_number, 1)
        self.assertEqual(decision.current_question_started_ms, 60_000)
        self.assertIsNone(decision.gathering_remaining_ms)
        self.assertEqual(decision.music_clock, MusicClock(0, NOW))
        self.assertEqual(
            decision.logical_transition_at, NOW + timedelta(seconds=60)
        )

    def test_late_observation_reconstructs_question_elapsed_from_boundary(self):
        observed_at = NOW + timedelta(seconds=75)
        decision = reconcile_music_timing(
            global_state="MUSIC_QUIZ",
            pause_resume_target=None,
            phase="gathering",
            music_clock=MusicClock(0, NOW),
            advent_clock=GameplayClock(44_000, None),
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=None,
            final_results_duration_ms=60_000,
            now=observed_at,
        )
        self.assertEqual(
            decision.logical_transition_at, NOW + timedelta(seconds=60)
        )
        self.assertEqual(
            music_phase_elapsed_ms(
                effective_music_ms(
                    decision.music_clock.accumulated_ms,
                    decision.music_clock.anchor,
                    observed_at,
                ),
                decision.current_question_started_ms,
            ),
            15_000,
        )

    def test_active_downtime_counts_toward_gathering(self):
        decision = reconcile_music_timing(
            global_state="MUSIC_QUIZ",
            pause_resume_target=None,
            phase="gathering",
            music_clock=MusicClock(25_000, NOW),
            advent_clock=GameplayClock(44_000, None),
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=None,
            final_results_duration_ms=60_000,
            now=NOW + timedelta(days=1),
        )
        self.assertEqual(decision.phase, "question")
        self.assertEqual(
            decision.logical_transition_at, NOW + timedelta(seconds=35)
        )

    def test_paused_gathering_freezes_then_resume_continues_music_time(self):
        advent_clock = GameplayClock(44_000, None)
        paused = pause_music_interruption(
            global_state="MUSIC_QUIZ",
            advent_clock=advent_clock,
            music_clock=MusicClock(10_000, NOW),
            underlying_teams=underlying_teams(),
            now=NOW + timedelta(seconds=20),
        )
        while_paused = reconcile_music_timing(
            global_state=paused.global_state,
            pause_resume_target=paused.pause_resume_target,
            phase="gathering",
            music_clock=paused.music_clock,
            advent_clock=paused.advent_clock,
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=None,
            final_results_duration_ms=60_000,
            now=NOW + timedelta(days=30),
        )
        self.assertEqual(while_paused.phase, "gathering")
        self.assertEqual(while_paused.gathering_remaining_ms, 30_000)

        resumed_at = NOW + timedelta(days=30)
        resumed = resume_music_interruption(
            global_state="PAUSED",
            pause_resume_target="MUSIC_QUIZ",
            advent_clock=advent_clock,
            music_clock=paused.music_clock,
            underlying_teams=underlying_teams(),
            now=resumed_at,
        )
        after_resume = reconcile_music_timing(
            global_state=resumed.global_state,
            pause_resume_target=resumed.pause_resume_target,
            phase="gathering",
            music_clock=resumed.music_clock,
            advent_clock=resumed.advent_clock,
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=None,
            final_results_duration_ms=60_000,
            now=resumed_at + timedelta(milliseconds=29_999),
        )
        self.assertEqual(after_resume.phase, "gathering")
        self.assertEqual(after_resume.gathering_remaining_ms, 1)

    def test_question_counter_is_derived_and_has_no_deadline(self):
        self.assertEqual(music_phase_elapsed_ms(65_432, 12_000), 53_432)
        decision = reconcile_music_timing(
            global_state="MUSIC_QUIZ",
            pause_resume_target=None,
            phase="question",
            music_clock=MusicClock(12_000, NOW),
            advent_clock=GameplayClock(44_000, None),
            current_question_number=7,
            current_question_started_ms=12_000,
            final_results_started_ms=None,
            final_results_duration_ms=60_000,
            now=NOW + timedelta(days=5),
        )
        self.assertEqual(decision.phase, "question")
        self.assertIsNone(decision.final_results_remaining_ms)

    def test_question_has_no_effect_at_or_far_beyond_three_minutes(self):
        for elapsed_ms in (180_000, 18_000_000):
            with self.subTest(elapsed_ms=elapsed_ms):
                decision = reconcile_music_timing(
                    global_state="MUSIC_QUIZ",
                    pause_resume_target=None,
                    phase="question",
                    music_clock=MusicClock(60_000, NOW),
                    advent_clock=GameplayClock(44_000, None),
                    current_question_number=6,
                    current_question_started_ms=60_000,
                    final_results_started_ms=None,
                    final_results_duration_ms=60_000,
                    now=NOW + timedelta(milliseconds=elapsed_ms),
                )
                self.assertEqual(decision.phase, "question")
                self.assertEqual(decision.current_question_number, 6)
                self.assertEqual(decision.current_question_started_ms, 60_000)
                self.assertIsNone(decision.logical_transition_at)

    def test_final_results_remain_until_exact_active_music_boundary(self):
        kwargs = {
            "global_state": "MUSIC_QUIZ",
            "pause_resume_target": None,
            "phase": "final_results",
            "music_clock": MusicClock(20_000, NOW),
            "advent_clock": GameplayClock(44_000, None),
            "current_question_number": None,
            "current_question_started_ms": None,
            "final_results_started_ms": 20_000,
            "final_results_duration_ms": 60_000,
        }
        before = reconcile_music_timing(
            **kwargs, now=NOW + timedelta(milliseconds=59_999)
        )
        self.assertEqual(before.phase, "final_results")
        self.assertEqual(before.final_results_remaining_ms, 1)

        boundary = reconcile_music_timing(
            **kwargs, now=NOW + timedelta(milliseconds=60_000)
        )
        self.assertEqual(boundary.global_state, "ADVENT_QUIZ")
        self.assertEqual(boundary.phase, "completed")
        self.assertEqual(boundary.music_clock, MusicClock(80_000, None))
        self.assertEqual(
            boundary.advent_clock,
            GameplayClock(44_000, NOW + timedelta(seconds=60)),
        )
        self.assertEqual(
            boundary.logical_transition_at, NOW + timedelta(seconds=60)
        )

    def test_pause_stops_final_display_time_and_resume_continues_it(self):
        paused = reconcile_music_timing(
            global_state="PAUSED",
            pause_resume_target="MUSIC_QUIZ",
            phase="final_results",
            music_clock=MusicClock(50_000, None),
            advent_clock=GameplayClock(44_000, None),
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=20_000,
            final_results_duration_ms=60_000,
            now=NOW + timedelta(days=9),
        )
        self.assertEqual(paused.final_results_remaining_ms, 30_000)
        self.assertEqual(paused.global_state, "PAUSED")

        resumed_at = NOW + timedelta(days=9)
        resumed = reconcile_music_timing(
            global_state="MUSIC_QUIZ",
            pause_resume_target=None,
            phase="final_results",
            music_clock=MusicClock(50_000, resumed_at),
            advent_clock=GameplayClock(44_000, None),
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=20_000,
            final_results_duration_ms=60_000,
            now=resumed_at + timedelta(seconds=29),
        )
        self.assertEqual(resumed.final_results_remaining_ms, 1_000)

    def test_restart_after_expiry_restores_advent_at_logical_instant(self):
        observed_at = NOW + timedelta(minutes=5)
        decision = reconcile_music_timing(
            global_state="MUSIC_QUIZ",
            pause_resume_target=None,
            phase="final_results",
            music_clock=MusicClock(100_000, NOW),
            advent_clock=GameplayClock(25_000, None),
            current_question_number=None,
            current_question_started_ms=None,
            final_results_started_ms=100_000,
            final_results_duration_ms=90_000,
            now=observed_at,
        )
        logical_expiry = NOW + timedelta(seconds=90)
        self.assertEqual(decision.logical_transition_at, logical_expiry)
        self.assertEqual(decision.advent_clock.anchor, logical_expiry)
        self.assertEqual(
            effective_gameplay_ms(
                decision.advent_clock.accumulated_ms,
                decision.advent_clock.anchor,
                observed_at,
            ),
            235_000,
        )

    def test_timing_rejects_impossible_state_clock_and_marker_pairings(self):
        base = {
            "global_state": "MUSIC_QUIZ",
            "pause_resume_target": None,
            "phase": "final_results",
            "music_clock": MusicClock(20_000, NOW),
            "advent_clock": GameplayClock(44_000, None),
            "current_question_number": None,
            "current_question_started_ms": None,
            "final_results_started_ms": 20_000,
            "final_results_duration_ms": 60_000,
            "now": NOW,
        }
        for changes, code in (
            ({"global_state": "ADVENT_QUIZ"}, "disallowed_state"),
            ({"music_clock": MusicClock(20_000, None)}, "invalid_input"),
            ({"advent_clock": GameplayClock(44_000, NOW)}, "invalid_input"),
            ({"final_results_started_ms": None}, "invalid_input"),
            ({"final_results_duration_ms": 0}, "invalid_input"),
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    error_code(
                        reconcile_music_timing,
                        **(base | changes),
                    ),
                    code,
                )

    def test_gathering_and_question_reject_invalid_marker_combinations(self):
        common = {
            "global_state": "MUSIC_QUIZ",
            "pause_resume_target": None,
            "music_clock": MusicClock(10_000, NOW),
            "advent_clock": GameplayClock(44_000, None),
            "final_results_duration_ms": 60_000,
            "now": NOW,
        }
        invalid_states = (
            {
                "phase": "gathering",
                "current_question_number": 1,
                "current_question_started_ms": None,
                "final_results_started_ms": None,
            },
            {
                "phase": "gathering",
                "current_question_number": None,
                "current_question_started_ms": 0,
                "final_results_started_ms": None,
            },
            {
                "phase": "gathering",
                "current_question_number": None,
                "current_question_started_ms": None,
                "final_results_started_ms": 0,
            },
            {
                "phase": "question",
                "current_question_number": None,
                "current_question_started_ms": 0,
                "final_results_started_ms": None,
            },
            {
                "phase": "question",
                "current_question_number": 12,
                "current_question_started_ms": 0,
                "final_results_started_ms": None,
            },
            {
                "phase": "question",
                "current_question_number": 1,
                "current_question_started_ms": None,
                "final_results_started_ms": None,
            },
            {
                "phase": "question",
                "current_question_number": 1,
                "current_question_started_ms": 10_001,
                "final_results_started_ms": None,
            },
            {
                "phase": "question",
                "current_question_number": 1,
                "current_question_started_ms": 0,
                "final_results_started_ms": 0,
            },
        )
        for state in invalid_states:
            with self.subTest(state=state):
                self.assertEqual(
                    error_code(
                        reconcile_music_timing,
                        **(common | state),
                    ),
                    "invalid_input",
                )

    def test_constant_matches_normative_question_count(self):
        self.assertEqual(MUSIC_QUESTION_TOTAL, 11)
        self.assertEqual(MUSIC_GATHERING_DURATION_MS, 60_000)
