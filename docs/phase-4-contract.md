# Phase 4 Music Quiz interruption contract

Status: complete and validated, 2026-09-24. Focused implementer coverage,
independent cross-cutting invariant review, deterministic SQLite race tests, and
the unchanged GitHub Actions full gate are green. Phase 5 is not authorized.

This contract is subordinate to
`christmas-2026-game-rules-state-semantics.md`. It uses only the phase-3 clock
contract and phase-3.1 active-run/snapshot recovery contract as supporting
implementation decisions. `Design.md`, `Views.md`, and `Game States.md` resolve
the otherwise implicit Music-pause and central-audio presentation details.

## Settled interruption and timer policy

### Entering and leaving Music

The first accepted canonical completion of either team's puzzle 13 enters
`MUSIC_QUIZ` in the **same SQLite `IMMEDIATE` transaction** as that completion.
Correct answer, immediate paid Skip, and admin force-completion all call the one
existing canonical completion pipeline; none owns a separate Music trigger path.

Entering Music:

- completes/rewards/advances the triggering team normally;
- reconciles and stops the phase-3 Advent-gameplay clock at the supplied server
  time;
- creates the run's unique durable Music record, initial two scores, and Music
  clock;
- preserves both `TeamRun.activity_state` values and Freeze start values exactly;
  and
- records completion and `music_started` audit facts before the transaction
  commits.

The unique Music record is the permanent one-time trigger marker. It is never
deleted or reset within a run. Retries, concurrent puzzle-13 completions, and a
later reopen/recompletion cannot create a second record or restart Music. If two
teams race to complete puzzle 13, the first transaction accepted by SQLite
completes and triggers Music; the waiter rereads `MUSIC_QUIZ` and cannot complete
an Advent puzzle during the interruption. A failure rolls back both completion
and trigger.

On normal Music completion, the exact underlying state resumes. "Exact" means
the triggering team's already-committed puzzle-13 completion is retained, while
neither team's activity state, Freeze start, Reverse, inventory, fragments, or
other Advent state is rewritten merely because Music began or ended. The Advent
clock is the sole mechanism which suspends Freeze duration during Music.

### Admin pause during Music

`Game States.md` explicitly permits `MUSIC_QUIZ -> PAUSED -> MUSIC_QUIZ`; this is
compatible with the normative requirement that both global interruptions
preserve underlying team state. Phase 4 therefore permits an administrator to
pause either active Advent or active Music. A durable pause-resume target records
which state was interrupted:

- pausing Advent retains the implemented phase-3 behavior and resumes Advent;
- pausing Music stops the Music clock, leaves the Advent clock stopped, and
  resumes the same Music question or final-results phase;
- `PAUSED` exposes no answer form and accepts no Music answer; and
- Reset may still end the active run under its existing lifecycle contract.

The migration backfills existing active/historical `PAUSED` rows with an Advent
resume target. A non-paused run has no pause-resume target. Constraints must
reject an impossible target/state pairing.

### Separate Music clock and final-result timer

Music owns a persisted accumulated millisecond clock plus nullable wall-clock
anchor, independent from the phase-3 Advent clock. It runs only while global
state is `MUSIC_QUIZ`, including the final-results phase. It stops under
`PAUSED`-from-Music. The optional per-question upward counter is derived from the
Music clock and has no deadline or effect on answer legality.

After question 11 resolves, the same winner transaction enters
`final_results`, persists its Music-clock start value, and clears the active
question. Final results remain for the snapshotted
`music_score_display_duration_ms`, then the logical global state returns to
`ADVENT_QUIZ` and the Advent clock resumes.

The settled recovery policy mirrors the recoverable phase-3 policy:

- intentional `PAUSED` time does not consume the final-results duration;
- unexpected downtime while persisted `MUSIC_QUIZ` **does** consume it;
- downtime while persisted `PAUSED` does not consume it;
- a restart before expiry recovers the same phase and remaining duration; and
- a restart/request after expiry observes Advent restored at the logical expiry
  instant, not at an arbitrary later browser request.

The final-results timer is not an Advent timer. At logical expiry the effective
Advent anchor is the expiry instant, so later downtime counts as Advent gameplay
under the phase-3 contract and Freeze remaining time changes only for time after
Music actually ended. Read projections may derive this effective transition
without taking the writer slot, as Freeze projections already do. Every later
mutation must first persist/reconcile the transition, clocks, Music completion,
and audit fact in its `IMMEDIATE` transaction before testing command legality.
No polling read may hold a writer transaction merely to advance the timer.

## Music rules and scoring

Each snapshotted run has exactly 11 Music questions shared by both teams.
Questions are sequential. Attempts on the active question are unlimited and
wrong attempts are persisted, receipt-backed, and penalty-free.

For each question, the first valid correct transaction accepted by SQLite:

1. verifies that the supplied run and Music question ID are current;
2. validates the answer from the immutable snapshot;
3. records the attempt and unique question result/winner;
4. increments the winner's separately persisted Music score by one question;
5. adds exactly the snapshotted `music_question_reward` to that team's normal
   private point balance;
6. immediately advances to the next question, or enters final results after 11;
7. records the receipt and audit event; and
8. commits all effects together.

The separately stored Music score is the number of questions won (0 through 11),
not a copy of the private normal balance. This makes the explicitly shareable
score a non-sensitive 11-question tally while preserving the normative configured
reward in the normal balance. Across both teams, score sum equals the number of
resolved questions.

A competing correct answer waits for the writer, then rereads the committed
question and rejects with `stale_question`; it receives no attempt-as-correct,
score, normal reward, advance, or success event. An invalid/rolled-back writer
wins nothing. Client timestamps and network arrival order are irrelevant.

Question IDs are mandatory anti-staleness tokens. A non-current, already
resolved, or pre-advance ID rejects as `stale_question`, including a delayed
answer that arrives after another team advanced the quiz. A current ID submitted
while Music is paused rejects as `disallowed_state`. Once there is no active
question (final results or restored Advent), answer submission rejects as
`disallowed_state`. Exact request-ID retries return the committed outcome without
replaying any attempt, result, score, reward, receipt, or event. While the run is
still active, the response carries a freshly derived projection so authoritative
clocks and timing remain current; after the run is archived, the recorded
projection is returned. Conflicting request-ID reuse rejects as `request_conflict`.

## Snapshot/package and audio contract

Schema version 4 retains the existing phase-3 fields and adds:

- nonnegative integer `music_question_reward`;
- positive integer `music_score_display_duration_ms`; and
- `music_questions`, exactly 11 sequential entries with unique safe `id`,
  nonempty `title` and `body`, a supported declarative `validator`, and one
  optional safe relative `audio` path.

All validators and audio are declarative snapshot data. Start validates and
snapshots referenced Music audio with the rest of the package; an active run
never rereads its source package. Existing v1-v3 snapshots remain readable, but
cannot supply a phase-4 Music trigger and must not silently invent Music data.

Music audio playback is centralized on the TV/overview, as preferred by
`Design.md`; team devices submit answers and do not auto-play audio. Phase 4 may
provide an optional current-question audio control/URL on the TV. It must never
auto-play future questions or expose their paths. The shared Music-media route
resolves only the active run's pinned snapshot and only the currently shareable
question; normal team puzzle media remains private and uses its existing
team-authorized route. Demo questions may use `audio: null`, so audio hardware or
licensed event content is not required for the phase gate.

## Application interfaces and projections

The architect owns concrete shared dataclasses in `quiz/contracts.py`. The
integrated public boundary is:

- `submit_music_answer(actor, SubmitMusicAnswer, *, now=None) -> MusicAnswerResult`;
- `get_team_state(actor, *, now=None) -> TeamProjection`, with an optional Music
  projection;
- `get_admin_state(actor, *, now=None) -> AdminProjection`, with the same
  authoritative Music status plus admin controls;
- `get_public_state(*, now=None) -> PublicProjection`; and
- existing `pause_game`, `resume_game`, all three completion routes, and Reset
  extended according to this contract rather than duplicated.

`SubmitMusicAnswer` contains UUID `request_id`, displayed `run_id`, displayed
Music `question_id`, and nonempty bounded `answer`. The authenticated session is
the sole source of team identity. `MusicAnswerResult.outcome` is `incorrect` or
`won`; rejections use existing stable `ApplicationError` codes.

The shared Music projection contains only:

- phase (`question` or `final_results`);
- question number and fixed total 11;
- the two `{team_id, score}` tallies;
- current-question elapsed milliseconds or final-result remaining milliseconds;
- the immediately previous winner, when useful for synchronized feedback; and
- safe current question presentation fields appropriate to that consumer.

The authenticated team variant additionally carries the opaque current
`question_id`, `title`, and `body` needed to submit. The TV variant may carry
`title`, `body`, and the authorized current audio URL, but needs no submission
ID. The admin variant may carry both. No variant contains an expected answer.

`PublicProjection` exposes conceptual global state and the approved Music
projection only. Outside active/paused Music it exposes no Advent team
progression, balances, effects, inventory, fragments, private puzzle fields, or
private media. During Music, normal point balances remain private; only Music
scores are the normative cross-team/public exception. Team projections never
contain the opposing team's private data. While `PAUSED`-from-Music, shared
status/scores may remain visible as read-only, but question submission and audio
playback controls are disabled.

Domain input/output values needed only by Music live in `quiz/domain/phase4.py`.
They accept explicit persisted values and explicit aware `now`/elapsed clock
values, return immutable decisions, and never access Django, the filesystem, or
the wall clock. Persistence maps those decisions; `quiz/application.py` calls
each policy once inside the authoritative transaction and remains the only
orchestration layer.

## Persistence and transaction contract

Migration `0005_phase4_music` follows `0004_retire_legacy_ready_runs`. The
approved logical schema is:

- a durable `Run` pause-resume target needed to distinguish paused Advent from
  paused Music;
- one `MusicQuiz` per run, whose existence is the trigger marker, with phase,
  current question number, Music clock accumulator/anchor, and final-result
  start marker;
- one `MusicScore` per run/team;
- at most one immutable `MusicQuestionResult` per run/question; and
- append-only `MusicAttempt` rows for accepted current-question attempts.

Database constraints enforce one Music quiz per run, valid teams, nonnegative
scores/clocks, score uniqueness, question-result uniqueness, winner validity,
phase/current-question consistency, and valid clock anchor/global-state pairing
where practical. Receipts and audit events use the existing run/actor/request
framework; schema constraints plus the `IMMEDIATE` transaction defend one reward
and one advance even if application checks regress.

Puzzle-13 trigger and Music answer transactions acquire `BEGIN IMMEDIATE` before
reading mutable run/question/team state. They then recheck actor, active run,
receipt, effective timer transition, legality and snapshot data; apply all live
state; write attempt/result/score/reward/receipt/audit; and commit or roll back as
one unit. Python locks and `select_for_update()` are not race guarantees.

Recovery uses only database state and the pinned immutable snapshot. Closing and
reopening application/database connections during a question, Music pause, and
final results must preserve question, winners, scores, normal rewards, clocks,
remaining display duration, trigger marker, and resume target.

## Exact ownership and edit order

Only one owner edits a named file at a time. The following assignments override
directory defaults for phase 4.

1. **Contract pass — architect (complete before specialist edits)**
   - owns `docs/phase-4-contract.md` only for this pass;
   - freezes the interfaces, schema shape, timer policy, and filenames below.
2. **Pure domain — `game_engine`**
   - owns `quiz/domain/phase4.py` and `tests/domain/test_phase4.py`;
   - implements Music/interruption transitions, clock decisions, legality,
     scoring/reward decisions, exact restoration and stale-question policy;
   - must not edit shared domain types, ORM, configuration, application, web,
     templates, migrations, demo data, or docs.
3. **Persistence/security — `persistence_security`**
   - owns `quiz/models.py`, `quiz/migrations/0005_phase4_music.py`,
     `quiz/configuration.py`, `quiz/web/music_media_views.py`,
     `tests/integration/test_phase4_storage.py`,
     `tests/integration/test_phase4_concurrency.py`, and
     `tests/security/test_phase4_storage_security.py`;
   - implements schema/constraints, schema-v4 validation/snapshot audio,
     transaction primitives needed by the agreed application boundary, current
     shared-audio authorization, durable receipts/attempts/results, and focused
     storage/security/concurrency tests;
   - must not edit application orchestration, shared contracts, general views or
     templates, demo data, or documentation.
4. **Integration — architect, after both handoffs stop**
   - owns `quiz/contracts.py`, `quiz/application.py`, `quiz/web/views.py`,
     `quiz/web/urls.py`, `quiz/templates/quiz/*`, `quiz/static/quiz/app.css`,
     `games/christmas-2026-demo/game.json`, any demo Music assets,
     `tests/integration/test_phase4_application.py`,
     `tests/browser/test_phase4_views.py`, `USER.md`, `docs/architecture.md`, and
     `implementation_plan.md`;
   - wires canonical completion, projections, 500 ms polling, central TV audio,
     and exactly 11 demo Music questions without reimplementing specialist rules.
5. **Independent verification — completed after integration**
   - `tests/integration/test_phase4_invariants.py` covers cross-boundary rollback,
     receipt/idempotency conflict behavior, interruption blocking, Reset/stale
     requests, and snapshot-only recovery after source deletion;
   - `tests/integration/test_phase4_full_music_journey.py` covers all 11 questions,
     exact score/reward totals, sequential advancement, and final-results state;
   - existing `test_phase4_concurrency.py`, phase-4 security tests, and browser
     tests were independently reviewed and retained for race/isolation/polling
     coverage rather than duplicated into parallel files;
   - no production file required reassignment from this review.

`quiz/application.py`, `quiz/contracts.py`, shared domain types, general routes,
templates, shared fixtures, settings, dependency/deployment files, and migration
ordering remain high-conflict architect-owned integration surfaces. Specialists
must report an incompatible interface instead of editing across ownership.

The edit order is contract; pure domain and schema/configuration work against it;
migration `0005`; architect application/contracts and routes; templates/polling;
demo package/docs; focused integration checks; one independent invariant pass;
then GitHub Actions. A failure returns only to the owner of the implicated rule or
file.

## Deterministic concurrency and browser requirements

Real-SQLite winner coverage must use a disposable file database and two separate
connections/threads. A synchronization hook/barrier makes A acquire the writer
transaction before B attempts the same displayed question; release A to commit,
then prove B rereads and rejects. Repeat with B designated first. Do not use
sleep, timestamp ordering, an in-memory database, sequential mocks, or
`select_for_update()` as substitutes. Each direction asserts exactly one winner,
one question result, one score increment, one configured normal reward, one
advance, and one winner event.

The same storage suite controls concurrent puzzle-13 completions sufficiently to
prove exactly one durable trigger/start event and no partial completion. Restart
tests close/reopen connections rather than reconstructing state from source
configuration.

Team and TV Music fragments keep the existing stable HTMX synchronization
container, poll every 500 ms with `drop`, and use `replace` for commands. The POST
returns the submitting team's new state; the other team and TV observe the
winner/scores/next question on polling. Browser coverage proves both browsers
synchronize, wrong answers do not advance, a stale held response cannot overwrite
a winning POST, a stale question POST cannot answer the next question, form
input/focus remains stable between unchanged polls, hidden-tab return refreshes,
and final-results/restored-Advent views switch without exposing private state.

## Phase-4 acceptance gate

Phase 4 is complete only when focused tests and unchanged GitHub Actions establish:

1. correct answer, paid Skip, and admin force-completion of current puzzle 13 all
   use canonical completion and trigger Music atomically;
2. concurrent puzzle-13 completion triggers exactly once, and the marker survives
   retries, reopening/recompletion, connection close, and restart;
3. Advent clock, both activity states, and active Freeze remaining duration are
   preserved exactly through Music and Music pause/resume;
4. all 11 snapshotted questions accept unlimited penalty-free wrong answers and
   advance immediately on the first accepted correct answer;
5. stale IDs, delayed answers, request conflicts, and post-resolution competitors
   cannot win, reward, or advance;
6. A-first and B-first separate-connection SQLite tests deterministically prove
   one winner, one separate score increment, one exact configured normal reward,
   one result/event, and one advance;
7. question state, scores, normal rewards, pause target, clocks, and trigger state
   recover from restart without rereading source configuration;
8. final results last the configured Music-active duration, stop during admin
   pause, count active-state downtime, and restore Advent from the logical expiry
   instant after restart;
9. public/TV and opposing-team reads expose only approved Music fields/current
   shared audio and never balances, progression, effects, answers, future audio,
   or private puzzle media;
10. both team browsers and the TV synchronize through the existing polling
    contract, including command/poll races and final restoration;
11. the demo schema-v4 package contains 13 sequential puzzles per team and exactly
    11 valid Music questions; and
12. phase-3/3.1 clock, Freeze, Reverse, isolation, lifecycle, snapshot and polling
    regressions remain green in the unchanged complete CI gate.

No phase-5 25-puzzle completion/global finish behavior, Challenge behavior,
public Advent progress percentages, broad media publication, advanced package
authoring/import/export, emergency recovery controls, deployment redesign, or
unrelated refactor belongs to phase 4.

## Contract-pass resolution record

No product decision remains blocking. The supporting-state Music pause path is
adopted; intentional pause stops Music/final-display time; active Music downtime
counts; expiry resumes Advent at its logical instant; Music score is a separately
persisted question-win tally; normal configured points are still awarded; the TV
is the sole automatic audio presentation; and public Advent data remains private.

## Integration and validation record

The bounded specialist handoffs and architect integration are present in the
working tree as of 2026-09-24. Migration `0005_phase4_music` implements the
durable trigger, pause target, clocks, attempts, results and scores. The shared
application boundary connects all three canonical completion routes, Music
answers, effective/persisted timer restoration, and team/admin/public projections.
The demo is schema v4 with 13 puzzles per team and 11 Music questions; its audio
fields are deliberately `null`.

Focused implementer evidence was green for Ruff, Django checks/migration drift,
36 phase-4 domain/storage/security/application tests, deterministic file-backed
A-first/B-first/concurrent-trigger SQLite tests, and Chromium synchronization.
The independent pass then added/verified:

- injected failure at the puzzle-13 Music trigger rolls back completion, reward,
  fragment, receipt, audit and trigger together;
- exact Music-answer retry cannot duplicate attempts/results/scores/rewards/events
  and conflicting request reuse is rejected;
- active Music blocks Advent answer/Skip/admin-completion/shop mutation paths;
- Reset archives Music state and makes old Music commands stale;
- an active Music run continues solely from its immutable snapshot after the
  source package is deleted; and
- a complete 11-question journey produces exactly 11 results, exact team scores
  and configured normal rewards, then enters final results.

Historical regression tests were also corrected without weakening their original
invariants: migration tests now restore the current schema after exercising old
migration targets, lifecycle initialization derives expected puzzle rows from the
pinned package rather than a two-puzzle constant, the legacy schema-v2 puzzle-13
boundary tests completion rather than reaching puzzle 13, and the TV browser
assertion checks rendered score structure.

GitHub Actions CI run #48 on the final code/test head was green: development image
build, Ruff, Django `check`, `makemigrations --check --dry-run`, and all 177 tests
passed, including domain, integration, security, real-SQLite concurrency and
Chromium browser coverage. No Phase-4 production defect remained from the
independent review.