# Phase 2 contract and ownership

Status: implemented and validated for phase 2, 2026-09-22. This contract was agreed before implementation; the normative game rules remain authoritative.

> **Lifecycle supersession (phase 3.1):** the Hint, Skip, pause/resume, point, completion, receipt, audit, authorization and transaction decisions in this contract remain valid. The phase-2 Reset/READY implementation described below is historical behavior and is superseded by `phase-3.1-contract.md`. After phase 3.1, full Reset deactivates the active run and leaves no replacement active run; `READY` is represented by the absence of an active run, and the next Start selects a source package and creates a fresh snapshot/new run.

> **Skip supersession (issue #45):** player Skip remains an immediate canonical completion route only for puzzles 1–24. Puzzle 25 is an explicit exception and must reject player Skip before cost deduction/completion. Correct-answer and administrator force-completion behavior for puzzle 25 is unchanged.

## Hint decision

There is one configured hint per puzzle and one durable reveal per `(run, team, puzzle)`. A team's first use on its accessible current puzzle consumes one generic Hint token and reveals that hint. An administrator's first reveal for a team's current puzzle reveals it without consuming a token. A new use after either reveal returns `already_revealed` without consuming a token or writing another reveal event; its no-op result is audited. Retrying the *same* request ID returns its original stored result. An absent configured hint rejects. Revealed text appears only in that team's current accessible puzzle projection; a different team never receives it. Unspent tokens survive progression. This settles the repeated-use ambiguity in `implementation_plan.md` without changing the specified first-use rule.

## Application contract

All mutations carry UUID `request_id` and displayed UUID `run_id`. Puzzle-specific mutations also carry the displayed `question_id`; admin mutations targeting a team carry `team_id` (`a` or `b`). The application verifies the authenticated actor in the database inside an SQLite `IMMEDIATE` transaction, then checks a same-actor, same-run request receipt before checking active run state. An exact retry returns the committed result; a changed payload with the same ID yields `request_conflict`. A new request against a reset/replaced run yields `stale_run`. No client-supplied team ID can select a team's identity for a team command.

Commands: `pause_game`, `resume_game`, `adjust_points` (signed nonzero integer delta), `force_complete_current`, `provide_hint`, `reset_game`, `purchase_hint`, `use_hint`, and `skip_current`. Admin commands require an admin actor; team commands require a team actor. Admin adjustments and full reset may act during `PAUSED`; only resume and reset can change the global state then. Team gameplay, admin force completion, and admin hint revelation require `ADVENT_QUIZ` and an underlying `PUZZLE` team state. Pause/resume changes only `Run.global_state`; team rows are preserved. Point removal, Hint purchase, and legal Skip reject insufficient points without writing an event, receipt, or balance change. Successful point events record `previous`, `delta`, and `new`.

Correct answer, legal immediate paid Skip on puzzles 1–24, and current-puzzle admin force completion all invoke one application persistence function around the existing pure `complete_puzzle` decision. Puzzle 25 player Skip is rejected before entering that completion path. Skip cost and completion reward occur in the same transaction and both are represented in the point change. No completion route can create duplicate rewards or fragments. Until phase 4, a package with puzzle 13 cannot advance from puzzle 12 into normal puzzle 13 gameplay; the application rejects that completion before cost/attempt effects. Phase 4 will implement the mandatory one-time Music interruption for all routes.

### Historical phase-2 Reset implementation

Phase 2 originally implemented full reset by atomically deactivating the old run and creating a new active `READY` run with a new UUID but the same immutable snapshot and package. The new run had fresh `READY` team rows at configured initial points, zero Hint tokens, current puzzle 1, and fresh incomplete progress; it had no reveal or one-time rows. The reset audit event belonged to the old run and identified the new run. A subsequent Start transitioned that `READY` run to `ADVENT_QUIZ` only when its package ID matched, setting both team activity states to `PUZZLE`.

This behavior remains part of the phase-2 historical handoff, but is no longer the target lifecycle. `docs/phase-3.1-contract.md` supersedes this subsection. Phase 3.1 keeps the important invariants—old commands become stale, audit history remains immutable, two administrators cannot create competing active runs—but removes the replacement READY run and reloads current source configuration only when a new Start is explicitly accepted.

## File ownership and edit order

1. Architect owns this contract, `quiz/contracts.py`, the shared error-code extension in `quiz/domain/types.py`, `quiz/application.py`, `quiz/web/views.py`, `quiz/web/urls.py`, `quiz/templates/quiz/*`, `quiz/static/quiz/app.css`, `games/christmas-2026-demo/game.json`, a mechanical answer-form selector update in `tests/browser/test_live_sync.py`, `USER.md`, and `implementation_plan.md`. These files have one editor at a time.
2. `game_engine` owns `quiz/domain/phase2.py` and `tests/domain/test_phase2.py`. It provides pure eligibility/cost/Hint decisions; no ORM, transactions, HTTP, or shared contract edits.
3. `persistence_security` owns `quiz/models.py`, the next sequential phase 2 migration, `quiz/configuration.py`, and `tests/integration/test_phase2_storage.py`. It adds configured `hint_price` and `skip_price` to the snapshotted package schema, durable Hint count/reveal and generic action receipts, with constraints. It does not edit application orchestration.
4. `test_invariants` owns `tests/integration/test_phase2_invariants.py` and `tests/security/test_phase2_isolation.py`. It verifies public application/HTTP contracts after integration, including spending/reset races, stale run/question, rollback, team isolation, admin authorization, and event history. It reports production defects to the file owner.

The architect integrates domain and persistence after their files are stable, then exposes web controls and updates documentation. No specialist concurrently edits shared files, existing shared fixtures, or another specialist's tests. Migration ordering is `0002` after phase 1 `0001_initial`.
