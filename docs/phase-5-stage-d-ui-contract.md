# Phase 5 Stage D UI-facing handoff

Status: Stage D integration contract for Stage E. The normative behavior and
privacy rules remain in `docs/phase-5-contract.md`.

## Projection fields

All Advent progress values are immutable `AdventProgressProjection` objects:

- `doors`: exactly 25 ordered `{number, status}` values; status is
  `completed`, `current`, or `future`;
- `completed_count`: integer from 0 through 25;
- `current_number`: nullable; it is null for a finished team; and
- `is_finished`: authoritative team-finish flag.

Team state exposes its own value as `state.advent_progress`, plus
`state.first_finisher_team_id` and `state.gameplay_elapsed_ms`. It retains its
existing private points, inventory, effects, fragments, and current question.
It never receives opponent progress.

Admin state exposes each team's value as `team.advent_progress`, and shared
`first_finisher_team_id` and `gameplay_elapsed_ms` at the top level. Existing
private admin facts and controls remain available.

Public state exposes `teams`, ordered A then B. Each item contains only
`team_id` and `advent_progress`. Its other shared fields are `global_state`,
`first_finisher_team_id`, `gameplay_elapsed_ms`, and the existing shared Music
projection. Do not add private puzzle content, answers/attempts, points,
fragments, hints/inventory, Reverse, Freeze, or private media.

The Django context also publishes `advent_progress` on team pages, `teams` on
public pages, and the two shared finish fields on team/admin/public pages.

## Commands and state identifiers

No new command endpoint is required. Existing endpoints remain canonical:

- `POST /team/answer/` for correct completion;
- `POST /team/action/skip/` for paid immediate Skip; and
- `POST /admin-game/action/force-complete/` for admin completion.

All three finish through the same application pipeline. Their existing success
outcome remains `completed`. A finished team has `team_state == FINISHED`, keeps
legacy `current_number == 25`, has no `question`, and has
`advent_progress.current_number == null`. Global completion is
`global_state == FINISHED` only after both teams finish.

## Polling and DOM boundaries

The 500 ms state endpoints and stable synchronization containers are unchanged.
Polls continue to use `drop`; command responses continue to use `replace`.

- Read-only clocks, calendars, and finish banners belong in normal poll targets.
- The answer pane context does not include first-finisher identity. Learning
  that the opponent finished therefore does not recreate the continuing team's
  still-valid answer input.
- The team action-pane context does include first-finisher identity because
  Freeze target eligibility changes when the opponent finishes.
- A team's own finish changes team/question context and removes its interaction
  panes. Admin team contexts likewise change with authoritative activity state.
- Public progress and finish labels are read-only and may update normally;
  current Music audio retains its separate context boundary.

Stage E owns templates, styling, responsive Advent/Music treatment, stable
finish labels, reduced-motion behavior, and focused browser acceptance. It
must not infer legality from these context strings or projection fields.
