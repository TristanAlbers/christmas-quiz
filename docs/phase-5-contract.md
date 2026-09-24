# Phase 5 complete progression and finish contract

Status: Stage A contract approved, 2026-09-24. Phase 4 is the implemented
baseline. Later Phase 5 stages must not change the rules below without a new
architect decision.

This contract is subordinate to `docs/product-decisions.md` and
`christmas-2026-game-rules-state-semantics.md`. `Design.md`, `Views.md`,
`docs/architecture.md`, the Phase 4 contract, and the polling guideline supply
the applicable presentation, recovery, and implementation boundaries.

## Progression, fragments, and finish semantics

- Normal progression remains strictly sequential and backend-authoritative.
  Correct answer, paid immediate Skip, and admin force-completion continue to
  call the single canonical completion pipeline.
- The artificial Phase 4 ceiling at puzzle 13 is removed. Puzzle 14 resumes
  only after the one-time Music interruption has ended; completing puzzles 14
  through 25 cannot retrigger Music.
- Completion marks, configured rewards, and non-null fragments commit exactly
  once. The team's ordered, cumulative fragment projection remains private and
  available while solving puzzle 25. Phase 5 adds no fragment templating,
  executable rule, or client-side answer derivation: puzzle 25 may instruct the
  team to combine its previously awarded declarative fragments.
- Only canonical completion of puzzle number 25 changes that team's activity
  state from `PUZZLE` to `FINISHED`. Its current number remains 25, puzzle 25 is
  `completed`, and no current question is projected. The completion command's
  existing successful outcome remains `completed`.
- The first team to finish creates the run's persistent first-finisher fact in
  the same transaction. Global state remains `ADVENT_QUIZ`; the Advent clock
  continues and the other team keeps its exact puzzle/effect/inventory state
  and may continue normal legal play.
- The second team to finish becomes `FINISHED` and changes global state to
  `FINISHED` in the same transaction. That transaction reconciles and stops the
  Advent clock. `FINISHED` is terminal in this phase except for existing full
  Reset; finished-team reopening is Phase 8 work.
- A finished team cannot answer, use/buy a Hint, Skip, buy Reverse, attack, or
  be targeted by Freeze. It cannot regain a normal interaction pane through a
  stale request, reload, resume, or timer reconciliation. Existing authorized
  admin/global lifecycle operations are not redefined here, but Phase 5 adds no
  finished-team correction control.

## Atomic order, durability, and audit

Both final-answer transactions acquire the established SQLite `IMMEDIATE`
writer slot before reading mutable state. The first valid transaction accepted
by the database wins: it completes/rewards puzzle 25, marks its team finished,
and inserts the sole first-finisher row atomically. A rolled-back or invalid
transaction wins nothing. A waiter rereads committed state and may then finish
the other team; client timestamps and request arrival order have no authority.

The logical persistence addition is one immutable `FirstFinisher` fact per run:
run (unique/protected), valid team ID, and server finish timestamp. Its insert is
guarded by a database uniqueness constraint. Team `FINISHED`, puzzle-25
completion/reward/fragment, first-finisher, possible global `FINISHED`, receipt,
and append-only audit facts commit or roll back together. Request-ID retries
return their prior outcome without duplicating any fact or award; conflicting,
stale, post-finish, and losing duplicate requests use existing stable rejection
behavior. Reset archives rather than deletes this history.

Audit history records puzzle completion plus `team_finished`; the winning
transaction also records `first_finisher`, and the second-finisher transaction
records `game_finished`. Restart/reload derives the same team/global states,
winner, stopped/running clock, fragments, and awards solely from the database
and pinned snapshot.

Package schema v5 has the schema-v4 fields and Music rules but requires exactly
25 sequential puzzles for each team. Earlier snapshots remain readable and are
never reloaded from source; they do not treat a shorter last puzzle as puzzle
25. The Phase 5 demo package advances to v5 and gives each team a distinct real
journey through Music to puzzle 25, with cumulative fragments used by its final
puzzle.

## Approved application projections and privacy

Use one immutable Advent progress value per projected team: 25 ordered doors,
each `{number, status}` where status is `completed`, `current`, or `future`, plus
`completed_count`, nullable `current_number`, and `is_finished`. Under Pause,
Music, or Freeze, doors describe the preserved underlying Advent progress.
Finished progress has 25 completed doors and no current door. Counts/percentages
are derived supplements, never substitutes for the doors.

The shared run finish fields are nullable `first_finisher_team_id` and
server-authoritative `gameplay_elapsed_ms`; global state supplies the final
result. Projection boundaries are:

- authenticated team: its own Advent progress, private points/inventory/
  effects/fragments/current puzzle, and the shared finish fields; never the
  opponent's progress or private state;
- authenticated admin: both teams' Advent progress and existing private admin
  facts/controls plus the shared finish fields; and
- public TV: both coarse Advent progress values and shared finish fields only.

The public exception does not include puzzle content/media, answers/attempts,
balances, fragments, hints/Hint inventory, Reverse, Freeze/hidden effects, or
private timing/details. First-finisher identity is visible after it exists. Team,
admin, and TV screens must make first-finisher and final-finish states persistent
and obvious; winner/confetti animation may enhance but must not replace a stable
label. Motion respects reduced-motion preferences.

## UI and polling acceptance

Team/admin target phone and tablet; public overview targets desktop/TV. Affected
surfaces establish one coherent readable Christmas shell and render actual
25-door Advent calendars with distinct completed/current/future and finished
states. They also retire inherited debt: a scannable 11-step Music tracker,
visual Hint-token and active-Reverse badges/cards, and a clearly styled immediate
Skip action. Decoration must preserve contrast, touch targets, clarity, and
privacy.

The 500 ms poll replaces read-only status, clocks, calendars, and finish banners.
It never replaces the stable synchronization container. Answer/Hint/Skip/shop
forms and admin controls remain mounted while their run, mode, question, and
permission context is unchanged. A team's own finish removes its interaction
panes; an opponent finishing changes Freeze-target eligibility and may replace
only that affected action pane. Merely learning the public winner must not reset
the continuing team's still-valid answer input. Commands retain `replace`, polls
retain `drop`, and context values are rendering hints, never authorization.

Focused browser acceptance uses representative 390x844 phone, 768x1024 tablet,
and 1920x1080 TV viewports. It proves 25 doors and clear finish states without
overflow/private leakage; continuing-team input node identity, focus, value, and
caret survive first-finisher polls; pointer-down/poll/pointer-up remains reliable
for a still-legal action; finish removes stale controls; Music shows 11 steps;
and Hint/Reverse/Skip have the required visual semantics.

## Ownership, edit order, and gate

1. **A architect:** owns this contract only and stops before implementation.
2. **B game engine:** owns `quiz/domain/` and focused `tests/domain/`; extends
   canonical completion/legality with pure final-team/global decisions.
3. **C persistence/security:** owns models, migration `0006_phase5_finish.py`,
   configuration, persistence helpers, and focused storage/concurrency/security
   tests; supplies the unique first-finisher claim and schema-v5 guarantees,
   without editing application or UI files.
4. **D integrator:** owns contracts, application orchestration, web projection/
   context boundaries, demo data, docs, and focused integration/full-journey
   tests. It consumes B/C decisions and leaves presentation styling to E.
5. **E UI experience:** owns templates, static presentation, and focused browser
   tests implementing every visual/device/polling requirement above.
6. **F invariant tester:** independently reviews full journeys, final-answer
   races, idempotency/rollback, recovery, isolation/public leakage, finished-team
   legality, device presentation, and polling interaction before CI.

The phase gate requires both distinct demo journeys to traverse real Music and
reach 25; one durable first finisher under reversed deterministic races; the
other team continuing while the winner is inactive; global finish only after
both; no duplicate reward/fragment/audit effects; reload/restart preservation;
strict projections; and all UI/browser acceptance above. Full GitHub Actions is
the final deterministic gate.
