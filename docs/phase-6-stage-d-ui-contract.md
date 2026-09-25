# Phase 6 Stage D UI-facing handoff

Status: Stage D integration contract consumed by the implemented Stage E UI. The
normative behavior, privacy rules, and visual acceptance remain in
`docs/phase-6-contract.md` and `docs/product-decisions.md`.

## Team projection and commands

`TeamProjection` adds these caller-private fields:

- `challenge_available`: whether this team's one free opportunity remains;
- `challenge_cost`: always `0` for schema-v6 packages, or null for pre-v6
  packages;
- `can_initiate_challenge`: a server-derived convenience value;
- `challenge_ineligible_reason`: null or `opportunity_spent`,
  `opponent_unavailable`, or `game_unavailable`; and
- `challenge`: null or the latest Challenge projection.

Each team may initiate at most one Challenge per run, so at most two Challenges
can occur. The package contains a different Challenge puzzle for each possible
initiator and those puzzles must not have the same ID or equivalent content.
Starting a Challenge never deducts points.

An active `challenge` contains `id`, `status == active`, caller `role`, `phase`,
and `grace_remaining_ms`. During the 15-second `starting` gathering phase its
`question` is null. When `phase == active`, `question` contains `id`, `title`,
`body`, and authorized `media_urls` for the puzzle bound to the initiating
team. A resolved projection contains `id`, `status == resolved`, role,
`winner_team_id`, and `freeze_applied`; its `question` is null. It exposes no
opponent attempts, answer, balance, inventory, or unrelated effect details.

Canonical endpoints are:

- `POST /team/action/challenge/` with `request_id` and `run_id`; and
- `POST /team/challenge-answer/` with `request_id`, `run_id`, `challenge_id`,
  `question_id`, and `answer`.

Initiation succeeds as `challenge_started`. Answers return `incorrect` or
`won`. An answer submitted before the gathering period expires is rejected as
`challenge_starting`. Other error responses may include `challenge_spent`,
`challenge_unavailable`, `stale_challenge`, `stale_question`, or
`disallowed_state`. The UI must show rejection text without treating derived
eligibility as authorization.

## Admin and public projections

Each `AdminTeamProjection` adds `challenge_available`. Top-level
`AdminProjection.challenge` is null or contains Challenge ID/status,
initiator/challenged team IDs, question ID, zero paid cost, phase, gathering
time remaining, Challenge number, winner, and whether the direct Freeze was
applied. There are no Phase 8 cancel/resolve controls.

During an active Challenge, `PublicProjection.challenge` drives a full overview
takeover similar to Music Quiz. It identifies the Challenge number and the
initiating/challenged teams. During `starting` it exposes the gathering state
and remaining grace time but withholds puzzle text. Once active it exposes only
the public puzzle title/body needed for the TV view. It never exposes the
answer, attempts, private team balances/inventory, private effect details, or
Challenge media. When the Challenge resolves, the public overview returns to
the normal Advent Quiz state.

## Polling and DOM boundaries

The existing 500 ms `drop` poll and command `replace` synchronization remain
canonical. Team `view_context` includes global/activity state plus Challenge
status, ID, phase, and question identity. The answer pane is therefore keyed by
run + Challenge + question and remains mounted across normal polls and wrong
attempts. The answer control is not rendered during the gathering phase. Pause,
resolution, Reset, or a changed Challenge identity may replace the pane.

Team `actions_context` includes opportunity, zero cost, derived eligibility,
and coarse reason. An initiation control remains mounted while those facts and
the existing run/mode facts are unchanged. A command response for an incorrect
Challenge answer deliberately sends no question-pane or action-pane OOB swap;
the active input keeps node identity, focus, value, caret, press, and touch
state. A win replaces both panes.

The implemented Stage E UI owns the Challenge/Sabotage templates, distinct
Christmas styling, responsive phone/tablet presentation, gathering/active/
result/Freeze semantics, public overview takeover, readable reason and
rejection copy, and focused browser acceptance at 390x844, 768x1024, and the TV
viewport. It uses the supplied contexts and endpoints rather than inferring
legality.
