# Christmas quiz implementation plan

Status: phases 1–3 complete as of 2026-09-23; phase 3.1 is planned next;
phases 4–9 are plans, not implemented features. This document alone does not authorize a new
phase. The prompts below authorize one named phase when the user submits them.
Do not start subsequent phases automatically. [USER.md](USER.md) describes what
can be used today.

## Recommendation and current baseline

Use phased implementation across multiple prompts/sessions. Start with one thin,
fully verified vertical slice; extend its working application through the later
mechanics. A phase is an acceptance boundary, not a promise that it fits one
context window. Continue an unfinished phase in another session using the resume
prompt below, without widening scope.

The repository now has working phases 1–3: synchronous Django/WSGI,
Compose app/dev targets, WhiteNoise, local HTMX, a public health endpoint,
two team and two admin logins, admin Start, the two-puzzle demo package,
snapshot-backed private media, persisted answer attempts/completion, audit,
idempotent receipts, WAL/IMMEDIATE SQLite transactions, 500 ms polling, and
domain/integration/security/Chromium tests. Phase 2 adds basic administration,
generic Hint tokens, and immediate Skip. Phase 3 adds the persisted Advent clock,
five-minute gameplay-time Freeze, admin Freeze/unfreeze, paid player Freeze
attacks, one active Uno Reverse, protected frozen reads, package schema version 3,
and simple polling views. Music Quiz, Challenges, full 25-puzzle content, and the
TV view are not implemented.

A lifecycle correction has been approved as phase 3.1. It changes the old
phase-2/phase-3 Reset model so `READY` means no active run, Reset ends/deactivates
the current run without creating a replacement, administrators select from the
available source packages, and Start creates a new immutable snapshot/new run.
This correction deliberately happens after phase 3 is green and before phase 4
so the completed phase-3 work is not destabilized.

Music Quiz, full 25-puzzle content, Challenge, the TV view, final package
authoring/import/export and emergency controls remain later phases.

The existing specifications and `docs/architecture.md` remain authoritative
as described in `AGENTS.md`. `docs/contracts-first-slice.md` records the
implemented first-slice API and ownership. Phase-specific contracts are
historical/implementation records; where `docs/phase-3.1-contract.md` explicitly
supersedes the Reset/READY lifecycle text in phase 2 or phase 3, the phase-3.1
contract is the current lifecycle target.

Read the current code and [USER.md](USER.md) before planning a later phase.
Preserve unrelated user edits and active runtime data. The four
`.codex/agents/*.toml` definitions match the current ownership roles.

## Rules for every implementation prompt

Read `AGENTS.md`, the normative game-rules/state-semantics document, the relevant
parts of `Design.md`, `Views.md`, and `Game States.md`, and
`docs/architecture.md`. Respect that specification ordering. The architecture
cannot override a normative rule. Inspect the current worktree and this plan
before edits; the inventory above will become historical as phases complete.

Read the contract for the phase being implemented plus any earlier contracts it
depends on. A later contract may explicitly supersede only a named portion of an
earlier implementation contract; do not discard unrelated earlier behavior.

`@architect` coordinates all phases and reviews integration. Before delegation,
record the phase's public contracts, exact production/test file assignments,
migration order, and shared-file edit order. Reuse existing specialist agents;
parallelize only non-overlapping files after agreeing contracts. Respect the
configured four-thread session limit: stage specialist work and independent
verification rather than requiring a root coordinator, architect, and all three
specialists to run simultaneously. The architect owns `quiz/application.py`,
`quiz/contracts.py`, settings/root routing, dependencies/deployment, shared
fixtures, and initial non-auth views/templates/static integration.
`@game_engine` owns deterministic domain policies and domain tests.
`@persistence_security` owns models/migrations, configuration/snapshots,
authentication and explicitly assigned private-media infrastructure.
`@test_invariants` owns independent adversarial/integration/browser verification.

Use the exact first-slice ownership table in `docs/contracts-first-slice.md` for
phase 1. The architect must additionally name owners for new account-management
commands, package fixtures, and media views before parallel edits. For later
phases, extend that table with actual filenames before coding; no specialist may
concurrently edit application orchestration, shared contracts, settings, routes,
migrations owned by another editor, or shared test fixtures. A specialist finding
a production defect reports it to its owner; test ownership does not grant
production ownership.

Every phase must deliver working UI for its newly exposed actions, backend
legality/isolation, atomic persistence, audit/idempotency where applicable, and
focused plus adversarial tests. Do not postpone security or persistence until a
later "hardening" pass. Keep simple Django functions/templates, authenticated
500 ms polling, SQLite, one application container, and persistent `./var` data.
Do not build an async/push stack or a generic command/repository framework.

Before handoff, report changed files, contracts/decisions, validation results,
unimplemented coverage, and remaining blockers. Update this plan's progress log
and relevant contract/architecture documentation. Do not call a phase complete
while its gate is untested or failing. Future phases do not authorize today's
code edits, automatic deployment to the live game, or invented final puzzle
content.

Keep [USER.md](USER.md) accurate as each user-facing behavior, configuration,
account, URL, package format, validation, or deployment change lands, not just
at phase handoff. Update `.env.example` at the same time whenever environment
variables or their requirements change. Treat these documentation edits as part
of the same phase, before its gate is declared complete; describe unavailable
controls explicitly instead of documenting a workaround that bypasses
application rules.

Update this plan's progress log **during** work, not only at final handoff.
Record a checkpoint after contract/ownership agreement, after implementation
milestones, after each meaningful validation batch or failure/fix, and before
turn end or a likely usage interruption when possible. Each checkpoint should
state current status, what changed, checks actually run with passes/failures/
skips, blockers, and the exact next action so another session can resume without
repeating completed work. Replace stale checkpoint text when a later result
supersedes it; do not mark a phase complete until its full gate has passed.

## Phase sequence and ready-to-paste prompts

Run these in order. Each prompt incorporates the rules above.

### 1. First authenticated, persisted vertical slice

Agents: `@architect`, `@game_engine`, `@persistence_security`, `@test_invariants`.
Prerequisite: scaffold inspection and fresh baseline validation.

Deliver a small development package with distinct Team A/Team B first puzzles,
answer validators, configurable initial/completion points, a hint definition,
a persistent fragment, and private media sufficient to test isolation. Label it
as demonstration data, not the authored Christmas game. Start opens puzzle 1 for
both teams; the acceptance journey exercises Team A progressing to puzzle 2 and
Team B remaining independent. Do not declare a two-puzzle demo globally finished.

Finalize the minimal contracts together before creating the first migration:
actors and projections; answer/completion inputs/results; package schema and
snapshot staging; receipt scope (including Start before a run exists); atomic
write and consistent-read strategy; account setup and role boundaries. Keep
credentials outside committed game content. Implement two team logins and two
named administrator accounts, simple admin Start, team state/answer views,
protected snapshot media, and synchronized polling. Snapshot both rules and
media. Supported operations cannot modify/delete the audit history.

Gate: every first-milestone criterion in `AGENTS.md`; wrong attempts persist;
correct completion/reward/fragment/progression/receipt/event commit together;
sequential prerequisites and team-private resources cannot be bypassed; retries
cannot duplicate rewards; conflicting/stale requests are rejected; injected
failure rolls back all writes; real file-backed SQLite contention is covered;
source package/media edits cannot alter an active run; reload and restart retain
state. Browser tests prove typing/focus survive polling, an answer POST actually
replaces a slow poll, old responses cannot overwrite it, and reconnect recovers.

```text
@architect Implement only phase 1 of implementation_plan.md: the authenticated,
persisted first vertical slice. Read AGENTS.md, the authoritative specs,
docs/architecture.md, and docs/contracts-first-slice.md; inspect and preserve the
current worktree. You may now edit code for this phase. Finalize minimal contracts
and exact ownership before delegating pure rules to @game_engine, storage/auth/
snapshots to @persistence_security, and independent adversarial/browser tests to
@test_invariants. Integrate the simple Start -> puzzle 1 -> persisted wrong answer
-> atomic correct completion -> puzzle 2 -> reload journey. Include private media,
immutable configuration, audit, idempotency, SQLite races, and polling acceptance.
Run the phase validation gate and update the plan with evidence. Stop after this
slice; do not implement later mechanics or polished calendars.
```

### 2. Basic administration, Hint inventory, and immediate Skip

Agents: all four. Prerequisite: phase 1 green.

Add admin pause/resume for normal Advent mode, atomic award/remove points, force
completion of the current puzzle, immediate admin hints, and full reset with audit
preservation and stale-run protection. Add configured Hint purchases, generic Hint
tokens that survive progression, Hint use, and immediate paid Skip. All completion
routes call the existing canonical pipeline. Build a simple two-team admin
projection and controls for these actions. Keep timer-dependent mechanics and
Music controls unavailable until their phases; do not enable a normal path beyond
puzzle 12 until phase 4 implements the mandatory puzzle-13 interruption.

Gate: no gameplay during pause; exact underlying team states resume; costs cannot
overspend under concurrent commands; Hint inventory and reveal privacy persist;
all three completion routes award once; admin-only actions reject team callers;
point events include previous/delta/new values; reset clears run state and
one-time markers, restores configured initial values, and preserves/logs history;
two admins cannot create competing active runs. Settle repeated Hint-use policy
before exposing that action (decision table below).

```text
@architect Implement only phase 2 of implementation_plan.md, after verifying the
first-slice gate is green. Coordinate @game_engine, @persistence_security, and
@test_invariants with explicit file ownership. Add basic pause/resume, admin point
adjustments, current-puzzle force completion, admin hints, full reset, Hint tokens,
and immediate Skip through the canonical completion pipeline. Resolve the listed
Hint contract before implementation. Keep all actions atomic, authorized, audited,
and covered by concurrent-spending/reset/stale-request tests. Do not bypass the
future puzzle-13 Music trigger or add attack/timer mechanics. Validate, document,
and stop at this phase's gate.
```

### 3. Recoverable gameplay time, Freeze, and Uno Reverse

Agents: all four. Prerequisite: phase 2 green and approved downtime semantics.

Before implementing the new timer/effect screens, establish the reusable visual
foundation for team/admin views: responsive application shell,
typography/spacing, buttons/forms/status components, team identity,
Advent/puzzle presentation, points/inventory presentation, and distinct
paused/frozen/interruption states. Keep this deliberately lightweight; final
artwork, animation and polish remain phase 7.

First settle the gameplay clock/restart contract. Implement server-owned persisted
time, 5-minute Advent-time Freeze, expiry, admin Freeze/unfreeze, configured Freeze
purchases, and one active Uno Reverse per team. The same canonical Freeze mechanic
serves the supported routes. Prepare/test interruption preservation with explicit
domain state inputs without exposing unfinished Music gameplay. Private puzzle
and hint responses, including media, must become inaccessible while frozen.

Gate: injected-time expiry boundaries, pause duration preservation, reconnect and
restart under the approved downtime policy; no duplicate Freeze/Reverse; atomic
cost and Reverse consumption; attacker pays when reversed; finished/ineligible
target rejection; client clocks cannot authorize expiry; timer reconciliation is
consistent across reads and competing commands. No long-lived polling write lock.

```text
@architect Implement only phase 3 of implementation_plan.md. Resolve and record
the pending gameplay-downtime and Freeze/Reverse routing decisions before dependent
code. Coordinate @game_engine for deterministic clock/effect policies,
@persistence_security for durable state and protected reads, and @test_invariants
for timer/restart/attack races. Integrate five-minute Advent-time Freeze, admin
unfreeze, Uno Reverse, and their simple views using the existing transaction and
polling contracts. Prove pause preserves remaining time and frozen teams cannot
retrieve hidden puzzle/hint/media content. Validate and stop at the phase gate.
```

### 3.1. Game selection and run lifecycle correction

Agents: `@architect`, `@persistence_security`, `@test_invariants`;
`@game_engine` only if inspection finds a genuinely pure lifecycle rule.
Prerequisite: phase 3 completely green with its handoff/documentation committed.

Read `docs/phase-3.1-contract.md` before implementation. This phase deliberately
corrects the old phase-2/phase-3 Reset model without reopening phase-3 gameplay
rules.

Treat `READY` as the application-level state with no active run. Full Reset
deactivates/ends the current run, preserves all history/audit/receipts and the old
immutable snapshot, and creates no replacement run. Team views show only a
waiting state while no run exists.

Add read-only discovery of available source packages under `games/`. Admins can
see valid packages and concise diagnostics for invalid packages. Merely listing
or validating packages must not create snapshots.

Start explicitly selects a package. It validates/stages a fresh immutable
snapshot from the package's current source files before the short writer
transaction, then atomically creates exactly one active run and initializes all
phase-2/phase-3 run state, including the gameplay clock.

Preserve the key recovery invariant: an application/container/host restart with
an active run always continues the same run and pinned snapshot. Never reread the
source package for an active run.

Provide a safe upgrade path for legacy active `READY` reset shells created by the
old implementation without requiring deletion of `quiz.sqlite3`.

Gate:

- active run survives restart with same run ID, snapshot, progression, balances,
  gameplay clock, Freeze and Uno Reverse;
- source package edits/deletion cannot alter/break an active run;
- Reset leaves no active run and preserves/logs old run history;
- old-run commands are stale after Reset;
- teams leak no prior state while waiting;
- admin READY view lists valid and invalid packages with actionable status;
- package discovery creates no snapshots;
- Start creates a new snapshot/new run from current selected source files;
- Reset + source edit + Start observes the new source through the new snapshot;
- concurrent Starts cannot create competing active runs;
- legacy active READY shells can be safely retired;
- the complete phase-3 regression gate remains green.

```text
@architect Implement only phase 3.1 of implementation_plan.md after confirming
phase 3 is fully complete and green.

Read AGENTS.md, the authoritative specifications, docs/architecture.md,
docs/phase-2-contract.md, docs/phase-3-contract.md,
docs/phase-3.1-contract.md, USER.md, and the final phase-3 handoff. Inspect the
current worktree before editing and preserve all completed phase-3 gameplay-clock,
Freeze, Uno Reverse, schema-v3, privacy and restart behavior. Do not begin phase 4
or Music Quiz work.

Implement the lifecycle contract exactly as documented:

- READY is the no-active-run condition; do not keep an active READY shell.
- Full Reset deactivates the current run, logs/preserves it and its immutable
  snapshot/history/receipts, and creates no replacement Run or team/progress rows.
- Team projections with no active run expose only a waiting-for-game-master READY
  state and no previous puzzle/points/inventory/effect/media data.
- Admin READY view discovers all source game packages under the configured games
  root. Discovery is read-only and must not create snapshots. Show invalid
  packages disabled with concise actionable administrator-only diagnostics.
- Start explicitly selects one package, validates/stages its current source
  configuration and referenced media outside the writer transaction, then
  atomically creates exactly one active run and initializes all phase-2/phase-3
  state from that fresh snapshot.
- An active run always uses its pinned immutable snapshot. Source edits/deletion
  cannot alter it.
- Application/container/server restart with an active run resumes that exact run;
  restart is never treated as Reset or package reload.
- Preserve the phase-3 downtime policy: active Advent downtime counts and paused
  downtime does not.
- Keep the one-active-run and request-id/idempotency invariants under simultaneous
  admin Starts/Resets.
- Implement a safe, idempotent compatibility path for legacy active READY shells
  created by the old Reset model without deleting the persistent database.
- Reuse the completed phase-3 package schema; do not introduce schema v4.
- Leave advanced package import/export/authoring polish to phase 7.

Coordinate @persistence_security for source-package discovery/validation and any
safe legacy-data migration/compatibility work. Coordinate @test_invariants for
restart/reset/start races, snapshot isolation, waiting-state privacy and browser
coverage. Avoid @game_engine production edits unless a pure lifecycle rule truly
requires them.

Update USER.md only after the new behavior works. Keep phase-2 and phase-3
contracts as historical records with explicit lifecycle-supersession notes rather
than rewriting their unrelated decisions.

Run the full phase-3.1 gate plus the complete applicable phase-3 regression suite,
update architecture/contracts/progress evidence, and stop. Do not start phase 4.
```

### 4. The puzzle-13 Music Quiz interruption

Agents: all four. Prerequisite: phase 3.1 green; Music pause/result-display
contracts resolved. Extend development data through puzzle 13 with 11 Music
questions.

All three completion routes trigger Music immediately and exactly once. Preserve
underlying team states and timer durations. Both teams answer the same active
Music question; wrong attempts are unlimited/penalty-free, the first accepted
correct transaction gets configured normal points, and question advancement is
immediate. Persist Music scores separately from normal balances. Show final scores
for the configured duration and resume Advent. Expose only authorized public Music
fields; private balances never enter the overview. Decide TV audio handling before
implementing playback; basic shared scores/question display need not wait for
public Advent percentages.

Gate: trigger via answer/Skip/admin, concurrent puzzle-13 completions, one-time
marker surviving retries, suspended Freeze restoration, stale Music question IDs,
all 11 questions, exact configured reward, display deadline/restart behavior, and
both browsers updating. Use controlled separate SQLite connections: hold A's
writer transaction while B submits, commit A, assert B rejects without extra
reward/advance, then repeat with B first. No sleep-based race ordering.

```text
@architect Implement only phase 4 of implementation_plan.md: the one-time
puzzle-13 Music Quiz. Confirm phase 3.1 is green first. Coordinate @game_engine,
@persistence_security, and @test_invariants after settling the documented Music
interruption and result-time contracts. Connect answer, Skip, and admin completion
to one atomic trigger; implement all 11 questions, first-valid-transaction
winners, configured normal-point rewards, public Music scores, and timed final
results followed by exact Advent restoration. Use deterministic real-SQLite winner
tests in both acceptance orders and browser synchronization tests. Validate and
stop at this phase's gate.
```

### 5. Complete 25-puzzle progression and the two-team finish

Agents: all four. Prerequisite: phase 4 green.

Extend demonstration data to 25 puzzles per team, distinct answers, and cumulative
fragments referenced by puzzle 25. Enforce all prerequisites. Persist the first
finisher and present the winner state immediately; the other team continues and
sees the explicit finish announcement. Only both completing puzzle 25 produces
global FINISHED. Preserve the first-finisher presentation. Test existing attacks,
shop, normal answers, and completed-run reset against finished-team restrictions.

Gate: complete two distinct team journeys through Music to 25; first finisher
cannot initiate/receive attacks or other gameplay; second team remains playable;
concurrent final answers yield one first-finisher record; no reward duplication;
reload/restart preserves the result; ordinary actions cannot reopen a team.

```text
@architect Implement only phase 5 of implementation_plan.md with @game_engine,
@persistence_security, and @test_invariants. Extend the working demonstration to
25 sequential puzzles per team with persistent fragments feeding the final puzzle.
Implement durable first-finisher behavior, the other team's continued play, and
global FINISHED only when both teams finish. Exercise the real puzzle-13 Music
path and all finished-team restrictions. Label sample content clearly, validate
both full journeys and the finish race, update the plan, and stop at this gate.
```

### 6. Challenge normal gameplay

Agents: all four. Prerequisite: phase 5 green; Challenge outcome/Reverse policy
resolved. Add one paid initiation opportunity per team and a shared Challenge
puzzle, unlimited penalty-free attempts, no deadline, first accepted correct
winner, and no Advent progression or point reward. Initiator victory freezes the
challenged team on Advent return; challenged-team victory resumes without Freeze.
Opportunity consumption and payment happen together. Finished teams cannot join.

Gate: eligibility, concurrent initiations/answers, exactly-once opportunity/cost,
no reward/progression, pause/reconnect/restart preservation, and both outcome
routes. A disconnect never resolves the Challenge. Cancellation is phase 8.

```text
@architect Implement only phase 6 of implementation_plan.md. Establish Challenge
contracts and explicit file ownership, then coordinate @game_engine,
@persistence_security, and @test_invariants. Build the paid once-per-team shared
Challenge, atomic first-correct winner, and specified no-points/no-progression
outcomes, preserving pause/reconnect state and applying Freeze through the agreed
canonical route. Include direct-request restrictions and real concurrency tests.
Do not implement emergency cancellation yet. Validate and stop at the phase gate.
```

### 7. Usable team/admin/TV views and package authoring

Agents: `@architect` (presentation/integration), `@persistence_security` (package
validation/media), `@test_invariants` (privacy/browser); `@game_engine` only for
necessary validator/declarative-rule extensions agreed in advance.
Prerequisite: normal gameplay phases green; public projection decision resolved
for any extra TV fields.

Turn the functional views into usable phone/tablet team and two-admin interfaces,
including calendar, shop/sabotage, fragments, distinct state screens, audit view,
and clear disabled/rejected actions. Keep rules on the backend. Create the TV
view with only approved fields; never reuse a private/admin projection. Frozen
screens must remove puzzle/hint content, not merely blur it. Add audio/image
presentation and TV playback if selected, including explicit operator interaction
where the browser requires it.

Build on the basic package discovery/selection implemented in phase 3.1. Document
the declarative package format with templates, richer validation diagnostics, and
a simple documented import/export workflow. Validate referenced assets, unknown
validators/effects, prerequisites, both teams' 25 puzzles, and 11 Music questions
for a release package. Reject unsupported executable behavior. Keep the small
demo/test package role explicit. Actual riddles, answers, media and physical
components require user-authored or separately requested content; placeholders
do not count as a completed event package.

Gate: required views on expected phones/tablets/TV, private/public response
allowlists, no answer leaks, stable input/focus under polling and media changes,
keyboard/touch use, package round trip, actionable invalid-package errors, and
snapshot stability after source deletion. UI polish must not alter any rule.

```text
@architect Implement only phase 7 of implementation_plan.md. Coordinate package/
media work with @persistence_security and independent privacy/browser verification
with @test_invariants; involve @game_engine only for explicitly agreed validator
extensions. Build the usable team calendars, admin controls/audit view, and public
TV projection without leaking private state. Resolve allowed public fields and TV
audio before dependent work. Extend the phase-3.1 package-selection foundation
with documented data-only authoring/import/export workflow and richer release
validation. Keep demonstration content labeled and list real event content still
needed. Validate views, polling, media, isolation, and package round trip; stop at
this gate.
```

### 8. Explicit emergency recovery controls

Agents: all four. Prerequisite: normal game and basic admin gates green; specific
emergency contracts resolved before dependent edits.

Add earlier-puzzle reopening and repair, finished-team reopening, team progression
reset, Challenge cancellation/refund/opportunity restoration, admin initiation/
resolution of Challenges, admin Reverse add/remove, and cancellation of supported
timers/effects. Translate older labels into canonical operations. Define supported
unusual-state corrections explicitly instead of providing an unrestricted state
editor. An earlier reopen leaves the current position/later rewards intact but
blocks dependent progression until repaired; provide an authorized way to answer
or repair the earlier puzzle. Historic rewards/fragments and Music trigger markers
prevent duplication. Define how each correction interacts with pauses, Music,
first-finisher records, and an already globally finished game.

Gate: emergency-operation permission checks and audit reasons; no accidental
rollback; re-completion cannot duplicate awards/fragments/Music; Challenge
cancellation refunds exactly once and restores opportunity; old commands cannot
mutate corrected context; all supported unusual-state corrections remain atomic.

```text
@architect Implement only phase 8 of implementation_plan.md. First settle and
document emergency reopen/reset/Challenge contracts, including current position,
prerequisite repair, historical awards, first-finisher state, interruption behavior,
and stale commands. Coordinate @game_engine, @persistence_security, and
@test_invariants with exact ownership. Implement the specified emergency controls
through canonical application operations, not direct database editing. Prove
atomic refunds, immutable audit, and no duplicate rewards/triggers. Validate and
stop at this gate; list any still-unsupported correction explicitly.
```

### 9. Backup/restore, deployment rehearsal, and event readiness

Agents: `@architect`, `@persistence_security`, `@test_invariants`; `@game_engine`
for confirmed domain defects only. Prerequisite: supported product phases green.

Deliver consistent SQLite backups together with referenced immutable snapshots,
restore commands/runbook, account and package setup, restart/upgrade guidance,
operator checks, and copying backups off the host. Rehearse on disposable data,
including restore into a clean runtime directory; never reset or replace a live
run as a verification shortcut. Validate offline static/media operation, Compose
persistence, permissions, expected two team/two admin/one TV load, and VPN/LAN
access on actual event devices. Record measured polling responsiveness rather
than introducing brittle timing assertions. Trace normative requirements to tests
and explicitly list gaps, including unprovided final puzzle content.

Gate: fresh deployment plus full-game rehearsal, restart during supported modes,
consistent backup/restore preserving state/receipts/audit/media, all applicable
checks green, and an operator-readable runbook. Event readiness additionally needs
the actual validated game package, working physical components/media, and device
rehearsal; generated demonstration content alone cannot satisfy it.

```text
@architect Implement only phase 9 of implementation_plan.md. Coordinate
@persistence_security for consistent database/snapshot backup and restore and
@test_invariants for independent recovery, isolation, browser, and full-game
rehearsal. Finish the operator runbook and requirement-to-test coverage report.
Use disposable runtime data for destructive recovery checks. Validate freshly
built images, offline operation, persistence, and expected device load; record
unrun home-server/device checks honestly. Do not change game rules to close gaps,
deploy over a live run, or claim event readiness without final content and device
rehearsal. Report the completed checks and remaining blockers.
```

## Decisions to settle at the phase that needs them

These are deferred questions, not authorization to invent behavior. First check
whether existing approved rules settle them. Record the architect's conclusion
and source; ask the user only for unresolved product/rule choices. Continue
independent work when a decision blocks only one part of a phase.

| Before | Decision / constraint |
| --- | --- |
| Phase 1 contract review | Finalize minimal package/validator schema, Start receipt scope before a run exists, account provisioning, and read/write transaction wiring. These are implementation decisions within the existing architecture, not known first-slice rule blockers. |
| Phase 2 Hint use | There is one hint per puzzle; the documents do not specify whether using another token after reveal consumes it. Define repeated use and admin/player reveal interactions explicitly, including receipt retries. |
| Phase 3 timers | Settled in `docs/phase-3-contract.md`: unexpected downtime counts while persisted state is `ADVENT_QUIZ`; paused downtime does not. |
| Phase 3/6 Freeze routes | Settled for phase 3 in `docs/phase-3-contract.md`: only paid player Freeze attacks trigger Reverse; admin Freeze applies directly. Challenge outcome uses the same direct-target policy unless its own phase uncovers a normative conflict. |
| Phase 3.1 lifecycle | Settled in `docs/phase-3.1-contract.md`: READY has no active run; Reset creates no replacement run; discovery is read-only; Start creates a fresh snapshot/run; restart recovers the existing active run. |
| Phase 4 Music | Supporting states permit pausing Music; the normative diagram does not specify that transition. Review whether it is permitted, which mode resumes, and whether final-score display duration stops during pause/downtime. Distinguish the result-display timer from suspended Advent gameplay timers. |
| Phase 4/7 public view | Normative isolation treats progression/points/effects as private; `Views.md` asks for public percentages. Music scores and the specified first-finisher announcement have explicit sharing rules. Obtain an approved projection before exposing extra Advent team data; show only permitted fields meanwhile. |
| Phase 4/7 audio | `Design.md` prefers central playback, while `Views.md` leaves playback from phones open. Choose the event playback workflow; define shared audio access separately from private puzzle media. |
| Phase 8 emergency | Define earlier-puzzle repair interaction, finished-team reopen/global-state/first-finisher behavior, progression resets, forced Challenge resolution, and operations during interruptions. Normal gameplay rules do not fully define these corrections. |

Already resolved by authority: Skip is an immediate action, Hint tokens are
generic inventory, puzzle status is `completed`, Freeze hides underlying
puzzle/hint content, global FINISHED waits for both teams, and Reset/restart are
distinct lifecycle operations. Do not re-open these decisions because older
implementation contracts differ.

## Validation workflow for implementation sessions

Use the existing Docker workflow. Sources are copied into images, not mounted as
live application code: rebuild both targets before validating changed code/tests.
Source game packages are bind-mounted read-only at runtime; package-only authoring
changes do not by themselves require rebuilding the application image, but code
or test changes do.

Use disposable test databases; tests must not mutate the persistent event run.
Read the current `docs/scaffold.md` and Compose configuration in case commands
have evolved. The following commands are for a development/disposable runtime
only: `up` may run migrations against the configured `./var`. If a live game
already exists, first use a separate Compose project and runtime-path override;
never replace or migrate that live runtime merely to validate a phase. With the
disposable local configuration already prepared:

```sh
docker compose --profile dev build app dev
docker compose up -d app
docker compose exec app python manage.py check
docker compose exec app python manage.py makemigrations --check --dry-run
docker compose run --rm --entrypoint ruff dev check .
docker compose run --rm dev test tests.integration.test_scaffold
```

Then run the smallest relevant Django domain/integration/security labels on the
fresh dev image. Use the existing concrete browser-test harness created in phase
1 for affected polling/view phases. Run the complete applicable suite at
integration/release gates, not repeatedly without a new change or unresolved
concern. Inspect `DEBUG=False` hashed static URLs, health, and actual application
pages when runtime behavior changes. If Docker/device access is unavailable,
record the exact unrun gate rather than claiming success from static inspection.

For phase 3.1 specifically, use disposable persisted runtime data to prove both
sides of the lifecycle distinction:

- restart an active phase-3 run and verify the exact run/snapshot/effects survive;
- Reset and verify there is no active run;
- edit a source package after Reset, Start it, and prove a new snapshot/run sees
  the new content;
- edit/delete source files during an active run and prove the active snapshot is
  unaffected;
- race two admin Starts using separate SQLite connections/requests;
- exercise the legacy READY-shell compatibility path on a database created by the
  old Reset implementation.

## Resume prompt for an unfinished phase

```text
@architect Resume the unfinished phase recorded in implementation_plan.md.
Inspect the worktree, progress log, contracts, and latest validation evidence;
preserve completed work and user edits. Reuse/delegate to @game_engine,
@persistence_security, and @test_invariants only for their remaining owned tasks.
Finish the current phase's acceptance gate, update documentation and validation
status, and stop. Do not restart scaffolding or begin the next phase automatically.
```

## Progress log

| Phase | Status | Evidence / next action |
| --- | --- | --- |
| Scaffold | Superseded by phase 1 implementation | Placeholder and health retained; scaffold tests included in the phase 1 run. |
| 1 | Complete | 2026-09-22: isolated Compose app/dev images rebuilt. App migrated/provisioned and restarted cleanly; `check`, `makemigrations --check --dry-run`, Ruff, 31 domain/integration/security tests on disposable file-backed SQLite, and 3 Chromium browser tests all pass with no skips. Health/index/login pages and DEBUG=False hashed CSS/HTMX JS return HTTP 200. Tests verify Team A journey to puzzle 2 after a persisted wrong answer, Team B isolation, receipts, audit/reward/fragment atomicity, rollback, snapshot recovery, SQLite writer contention, focus under polling, command versus slow poll, and reconnect. A separate live-process restart on disposable runtime preserved the run ID, puzzle 2, 7 points, fragment, 2 attempts/receipts and 3 audit events. Existing `./var` runtime was not used for validation. |
| Current-use documentation | Complete | 2026-09-23: `USER.md` covers phases 1–3, including setup, accounts, team play, admin controls, Hint/Skip/Freeze/Reverse actions, the persisted clock and downtime policy, package authoring, private snapshots, restart behavior, and validation. The TV view and later mechanics remain unavailable. README points to the guide. Credential rotation requires container recreation; `.env.example` needs no phase-3 changes. Phase 3.1 must update `USER.md` only when its new behavior actually lands and validates. |
| 2 | Complete | 2026-09-22 final isolated image gate passed: `manage.py check`, `makemigrations --check --dry-run`, full Ruff, 63 domain/integration/security tests (40.456 s), and 3 Chromium browser tests (9.928 s), with zero failures/skips. Disposable app healthy; `/health/`, `/`, `/login/`, `/admin-login/`, hashed CSS, and local HTMX JS returned HTTP 200. `git diff --check` passed. `docs/phase-2-contract.md` remains the historical phase-2 contract; its old replacement-READY-run Reset model is explicitly superseded for future behavior by phase 3.1. |
| 3 | Complete | 2026-09-23: the persisted Advent clock, five-minute Freeze, admin Freeze/unfreeze, paid player Freeze attacks, one active Uno Reverse, protected frozen reads, and simple polling views are implemented. `docs/phase-3-contract.md` records the downtime and routing decisions. Fresh Compose-image validation passed Django checks, migration consistency, full Ruff, 107 domain/integration/security tests, 7 Chromium browser tests, and `git diff --check`, with zero failures/skips. Controlled file-backed SQLite tests cover pause/restart preservation, expiry reconciliation, competing purchases/attacks, atomic Reverse consumption, and polling without a writer lock. Next action is phase 3.1. |
| 3.1 | Planned next | Lifecycle correction is specified in `docs/phase-3.1-contract.md`: no-active-run READY, Reset without replacement run, read-only package discovery, explicit package selection, fresh snapshot/new run on Start, safe legacy READY-shell compatibility, and restart preservation. |
| 4–9 | Not started | Dependent on phase 3.1 and the preceding gates/decisions above. |

For each implementation handoff, add the actual phase status, changed interfaces,
checks run with pass/fail/skipped status, unimplemented acceptance cases, any
required user decision, and the exact next action. Keep the inventory and prompts
aligned with the final accepted implementation rather than abandoned approaches.

### Phase 1 handoff, 2026-09-22

Implemented `quiz.contracts` values and `quiz.application` Start/state/answer
functions; pure domain answer/completion decisions; the first Django schema,
account-role mapping and provisioning command; data-only demo package with
snapshotted private PNG assets; authenticated admin/team/media views; and 500 ms
HTMX polling. The package is explicitly demonstration content, with only two
puzzles per team. Completing puzzle 2 does not finish a team or the global game.
No phase 2 mechanics or calendar polish were added.

Validation used a separate Compose project, `/tmp/christmas-phase1-var` mounted
at `/app/var`, and disposable `TEST_DATABASE_PATH` files. Fresh image checks:
`manage.py check` passed; `makemigrations --check --dry-run` reported no changes;
`ruff check .` passed; 31 domain/integration/security tests passed; 3 Chromium
tests passed. No tests skipped. After creating a run and submitting one wrong
and one correct answer on the isolated app, a Gunicorn container restart
preserved puzzle 2, 7 points, its fragment, the two attempts and receipts, and
all three audit events. Health/index/login and both hashed static assets
returned HTTP 200. `git diff --check` passed.

Known phase 1 implementation limit: every answer currently verifies the
snapshot manifest and all referenced media bytes while holding SQLite's writer
slot. This is short for the two tiny demo assets, but should be measured before
using a large event package; see `docs/architecture.md`. Aborted or losing Start
attempts may leave an unreferenced staged snapshot directory; it cannot affect
active-run reads, and cleanup can be added with the future reset/maintenance
workflow. No rule ambiguity or user decision blocks this slice.

At this phase-1 handoff, the next action was to begin phase 2 with a separate
prompt and resolve its repeated Hint-use contract. Phase 2 is now complete;
the demo package remains demonstration content, not finished event content.

### Phase 2 handoff, 2026-09-22

Implemented basic admin pause/resume, signed point adjustments, current-puzzle
force completion, immediate admin Hint reveal, full reset, team Hint purchases
and use, and immediate paid Skip. Correct answers, Skip, and admin force
completion share one application completion persistence path and the pure domain
completion policy. Every successful phase-2 command commits its result, receipt,
and audit event in an SQLite `IMMEDIATE` transaction. Hint tokens and reveals
are durable and team-private.

The phase-2 implementation of Reset preserved the old run/audit trail while
creating a new active READY run from the same immutable snapshot, with fresh
configured initial values. That is retained as historical implementation
evidence, but its lifecycle semantics are superseded by the planned phase 3.1
contract. Phase 3.1 will instead leave no active run after Reset and make the
next Start explicitly select/stage a fresh source package.

All three completion routes stop before opening puzzle 13 until the mandatory
Music interruption is implemented.

`docs/phase-2-contract.md` records the settled Hint rule, commands, errors, file
ownership, migration order and historical reset model. The demo package is schema
version 2 with configurable Hint and Skip prices. Version 1 snapshots remain
readable but cannot use those price-dependent actions. `USER.md` documents the
available phase-2 controls and limits. Domain, storage, adversarial, security,
HTTP, and browser tests cover the phase-2 gate, including concurrent spending,
competing resets, stale requests, authorization, Hint privacy, exactly-once
completion, and the puzzle-13 boundary.

Validation used rebuilt isolated Compose images, disposable file-backed SQLite,
and a disposable app runtime. `manage.py check`, migration consistency, full
Ruff, 63 domain/integration/security tests, 3 Chromium browser tests, health,
index/login pages, hashed CSS/HTMX assets, and `git diff --check` all passed.
No tests skipped. No live game runtime was touched.

### Phase 3 handoff, 2026-09-23

Implemented one persisted Advent-gameplay clock per run, deterministic clock and
effect policies, five-minute gameplay-time Freeze, logical expiry on reads with
transactional reconciliation on commands, direct admin Freeze/unfreeze, paid
player Freeze attacks, and one durable paid Uno Reverse per team. All mutations
retain the existing UUID receipt, audit, stale-run, actor recheck, and SQLite
`IMMEDIATE` transaction contracts. Team/admin projections and 500 ms polling
views expose only authorized effect state; frozen and paused teams cannot obtain
their puzzle, revealed Hint, answer/shop controls, or private media.

`docs/phase-3-contract.md` settles the two prerequisite decisions. Unexpected
downtime counts while persisted state is `ADVENT_QUIZ`; paused downtime does not.
Only a valid paid player Freeze attack consumes and redirects Uno Reverse, while
admin Freeze and the future Challenge-loss route apply directly. The attacker
still pays on a reversed attack. Schema version 3 snapshots pin nonnegative
`freeze_cost` and `uno_reverse_cost`; version 1/2 snapshots remain readable but
cannot use mechanics whose cost was not snapshotted.

Validation used freshly rebuilt Compose images and disposable file-backed SQLite.
`manage.py check`, `makemigrations --check --dry-run`, full Ruff, 107
domain/integration/security tests, 7 Chromium browser tests, and
`git diff --check` passed with zero failures or skips. Focused specialist evidence
also included 22 deterministic domain tests, 7 storage tests, 21 combined
storage/isolation/race tests, and 16 adversarial/browser gate tests. Controlled
writer contention proves one Reverse/purchase outcome and no double charge;
restart, pause, exact expiry, protected media, forged client timing/target data,
and read-path locking are covered. No live game runtime was used.

No Phase 4 Music behavior, Challenge behavior, final content, or TV overview was
added. There are no unresolved Phase 3 blockers. Phase 3.1 is the next approved
lifecycle correction; phase 4 still requires a separate prompt and resolution of
its documented Music decisions.
