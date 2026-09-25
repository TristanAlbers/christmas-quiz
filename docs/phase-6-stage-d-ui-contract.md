# Phase 6 Stage D UI-facing handoff

Status: Stage D integration contract for Stage E. The normative behavior,
privacy, and visual acceptance remain in `docs/phase-6-contract.md`.

## Team projection and commands

`TeamProjection` adds these caller-private fields:

- `challenge_available`: whether this team's one opportunity remains;
- `challenge_cost`: the snapshotted cost, or null for pre-v6 packages;
- `can_initiate_challenge`: a server-derived convenience value;
- `challenge_ineligible_reason`: null or `opportunity_spent`,
  `insufficient_points`, `opponent_unavailable`, or `game_unavailable`; and
- `challenge`: null or the latest Challenge projection.

An active `challenge` contains `id`, `status == active`, caller `role`, and a
shared `question` with `id`, `title`, `body`, and authorized `media_urls`. A
resolved projection contains `id`, `status == resolved`, role,
`winner_team_id`, and `freeze_applied`; its `question` is null. It exposes no
opponent attempts, answer, balance, inventory, or effect details.

Canonical endpoints are:

- `POST /team/action/challenge/` with `request_id` and `run_id`; and
- `POST /team/challenge-answer/` with `request_id`, `run_id`, `challenge_id`,
  `question_id`, and `answer`.

Initiation succeeds as `challenge_started`. Answers return `incorrect` or
`won`. Error responses may include `challenge_spent`, `challenge_unavailable`,
`stale_challenge`, `insufficient_points`, `stale_question`, or
`disallowed_state`. The UI must show rejection text without treating derived
eligibility as authorization.

## Admin and public projections

Each `AdminTeamProjection` adds `challenge_available`. Top-level
`AdminProjection.challenge` is null or contains Challenge ID/status,
initiator/challenged team IDs, question ID, paid cost, winner, and whether the
direct Freeze was applied. There are no Phase 8 cancel/resolve controls.

`PublicProjection` and both overview contexts are unchanged. Challenge status,
content, result, opportunity, payment, attempts, private effects, and media
must not appear in TV responses or DOM.

## Polling and DOM boundaries

The existing 500 ms `drop` poll and command `replace` synchronization remain
canonical. Team `view_context` now includes global/activity state plus
Challenge status, ID, and question ID. The answer pane is therefore keyed by
run + Challenge + question and remains mounted across normal polls and wrong
attempts. Pause, resolution, Reset, or a changed Challenge identity may replace
it.

Team `actions_context` now includes opportunity, cost, derived eligibility,
and coarse reason. An initiation control remains mounted while those facts and
the existing run/mode facts are unchanged. A command response for an incorrect
Challenge answer deliberately sends no question-pane or action-pane OOB swap;
the active input keeps node identity, focus, value, caret, press, and touch
state. A win replaces both panes.

Stage E owns the Challenge/Sabotage templates, distinct Christmas styling,
responsive phone/tablet presentation, active/result/Freeze semantics, readable
reason and rejection copy, and the focused 390x844 and 768x1024 browser tests.
It should use the supplied contexts and endpoints rather than infer legality.
