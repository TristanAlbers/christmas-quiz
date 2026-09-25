# Phase 3 clock, Freeze, and Reverse contract

Status: implemented and validated for phase 3, 2026-09-23. The normative game
rules remain authoritative.

> **Lifecycle supersession (phase 3.1):** the gameplay-clock, Freeze, Uno Reverse,
> privacy, package-schema-v3 and transaction decisions in this contract remain
> valid. The statements below that assume Reset creates a new active `READY` run
> are historical phase-3 behavior and are superseded by
> `phase-3.1-contract.md`. After phase 3.1, a full Reset ends/deactivates the
> active run and leaves no replacement run; the next Start creates a new run and
> starts its gameplay clock from a freshly staged snapshot of the selected source
> package.

## Settled decisions

### Gameplay clock and unexpected downtime

Each run owns one persisted Advent-gameplay clock. It stores accumulated elapsed
milliseconds plus an optional wall-clock anchor while `ADVENT_QUIZ` is active.
Entering `PAUSED` reconciles elapsed gameplay time at the supplied server time and
clears the anchor. Resuming installs a new anchor without changing accumulated
time. The same stop/start contract is reserved for the later `MUSIC_QUIZ`
interruption.

Unexpected application/server downtime **counts as Advent gameplay time when the
persisted global state is `ADVENT_QUIZ`**: the persisted anchor remains in force,
so restart derives elapsed time from the authoritative server clock. Downtime does
not count when the persisted state is `PAUSED`, because the anchor was cleared
when pause committed. This is recoverable without an unverifiable process-liveness
history and preserves a deliberately paused game across restarts. Backward wall
clock movement is clamped so gameplay time never decreases.

Poll/read paths derive the effective clock and expired Freeze state without a
write transaction. Every mutating use case reconciles expired Freezes inside its
existing SQLite `IMMEDIATE` transaction before checking eligibility. Thus a poll
never holds the writer slot, while commands and projections use the same pure
boundary rule: a Freeze is active exactly while elapsed gameplay time is less
than its start plus 300,000 ms.

### Canonical Freeze routes and Uno Reverse

There is one five-minute Freeze mechanic and no Freeze inventory. A player Freeze
action immediately pays the snapshotted `freeze_cost` and attacks the opposing
team atomically. Only this player attack route is Reverse-eligible, because the
normative Reverse rule is explicitly defined for an attacker and says that the
attacker still pays.

Admin Freeze and the future Challenge-loss outcome use the same duration,
eligibility, timer, state transition, and expiry policy, but apply directly to
their named target and do not consume or redirect an Uno Reverse. This preserves
the normative requirement that a Challenge loser receives a Freeze and keeps an
administrative intervention deterministic when there is no paying attacker.
Admin Freeze/unfreeze is permitted in `ADVENT_QUIZ` or `PAUSED`; a Freeze applied
while paused starts at the stopped gameplay-clock value.

A player Freeze attack is rejected with `already_active` when its opposing target already has an active Freeze; the rejected attack does not charge points or write a successful command/event.

A team purchase of Uno Reverse immediately deducts the snapshotted
`uno_reverse_cost` and activates its single durable Reverse. A second purchase
while active is rejected. It remains active until a valid player Freeze attack
targets that team, at which point the same transaction consumes it, charges the
attacker, leaves the target unaffected, and Freezes the attacker. Reverse status
is private to its owning team and administrators.

## Public application contract

All mutations retain the phase-2 UUID `request_id`/`run_id` receipt contract,
database actor recheck, stale-run handling, audit event, and one SQLite
`IMMEDIATE` transaction. New commands are:

- `freeze_opponent(actor, RunCommand, *, now=None)` for the immediate paid team
  attack;
- `purchase_uno_reverse(actor, RunCommand, *, now=None)`;
- `admin_freeze(actor, AdminTeam, *, now=None)`;
- `admin_unfreeze(actor, AdminTeam, *, now=None)`.

`now` is an optional aware server datetime used for deterministic tests; web
callers omit it. Pause, resume, projections, answer/shop/completion commands, and
private-media authorization use the same clock input/policy. Team projections add
private `uno_reverse_active`, `freeze_remaining_ms`, `freeze_cost`, and
`uno_reverse_cost`. Admin team projections expose effect status and remaining
time. Frozen projections contain no question, hint, or media URL.

Stable rejection codes add `already_active` for duplicate Reverse/Freeze
activation. Insufficient funds, interruption state, finished/ineligible targets,
and stale/duplicate requests retain the existing error/receipt rules. Rejected
commands do not charge points, consume Reverse, or write success receipts/events.

## Persistence and package contract

Migration `0003_phase3` follows `0002_phase2`. `Run` gains the persisted gameplay
clock accumulator/anchor. `TeamRun` gains a nullable Freeze start on that clock
and a Boolean Reverse flag, with constraints defending valid nonnegative/pairing
state. The package advances to schema version 3 and requires nonnegative integer
`freeze_cost` and `uno_reverse_cost`. Existing v1/v2 snapshots remain readable,
but phase-3 purchases are unavailable for them.

During the original phase-3 implementation, Reset created a stopped READY clock
on a replacement active run and Start of that READY run started its clock. That
lifecycle is superseded by phase 3.1: Reset now deactivates the old run and
creates no replacement. A later Start creates a new run from a newly staged
snapshot and initializes that new run's stopped/starting gameplay clock according
to the existing phase-3 clock policy. Existing historical runs keep their stored
clock/effect data unchanged.

## Ownership and edit order

1. `architect` owns this contract, `docs/architecture.md`, `quiz/contracts.py`,
   `quiz/application.py`, `quiz/web/views.py`, `quiz/templates/quiz/*`,
   `quiz/static/quiz/app.css`, `games/christmas-2026-demo/game.json`, `USER.md`,
   and `implementation_plan.md`. These shared/integration files have one editor.
2. `game_engine` owns `quiz/domain/phase3.py` and
   `tests/domain/test_phase3.py`. It supplies deterministic gameplay-clock,
   Freeze, attack/Reverse, and purchase decisions without ORM/HTTP changes.
3. `persistence_security` owns `quiz/models.py`,
   `quiz/migrations/0003_phase3.py`, `quiz/configuration.py`,
   `quiz/web/media_views.py`, and `tests/integration/test_phase3_storage.py`.
   It implements durable/constraint-backed fields, schema v3, and protected
   media authorization using the agreed pure clock policy. It does not edit
   application orchestration or shared contracts.
4. `test_invariants` owns
   `tests/integration/test_phase3_invariants.py`,
   `tests/security/test_phase3_isolation.py`, and
   `tests/browser/test_phase3_views.py`. It verifies only public behavior after
   integration and reports production defects to the owner.

Domain and persistence work may proceed in parallel against this contract.
Application integration follows their stable interfaces; adversarial tests are
then completed against the integrated API. No phase-4 Music gameplay or later
mechanic is included.
