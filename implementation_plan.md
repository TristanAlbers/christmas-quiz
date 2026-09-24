# Christmas quiz implementation plan

Status: phases 1–3.1 are complete and validated as of 2026-09-23. Phases 4–9 are plans, not implemented features. This file does not authorize a new phase by itself; a user prompt authorizes one named phase. Never start the next phase automatically.

`USER.md` describes the currently usable product. Historical implementation detail for completed phases is recorded in `docs/contracts-first-slice.md`, `docs/phase-2-contract.md`, `docs/phase-3-contract.md`, `docs/phase-3.1-contract.md`, architecture documentation, and Git history. Future implementation sessions should not reread completed-phase handoffs unless the current phase depends on a specific historical contract or a failure makes that evidence relevant.

## Current baseline

The repository has working phases 1–3.1:

- synchronous Django/Gunicorn WSGI, Django templates, local HTMX, WhiteNoise, Compose, SQLite;
- two isolated team logins and two named administrators;
- immutable package snapshots and protected private media;
- persisted attempts/completion, audit, receipts, WAL/IMMEDIATE transactions;
- 500 ms polling with stable interactive controls;
- admin pause/resume, point adjustments, force completion, hints, Hint tokens, immediate Skip;
- persisted Advent gameplay clock, Freeze, admin Freeze/unfreeze, paid Freeze attack, one Uno Reverse;
- no-active-run `READY`, archival Reset, source-package discovery/selection, fresh snapshot/run Start, safe retirement of legacy READY shells;
- domain/integration/security/Chromium coverage for implemented behavior.

Music Quiz, 25-puzzle completion, Challenges, final team/admin/TV views, final package authoring workflow, emergency recovery controls, and event-readiness/backup work remain future phases.

## Rules for every future implementation phase

Preserve the authority and invariants in `AGENTS.md`. Read the current phase section, current code, `USER.md`, `docs/architecture.md`, and only the authoritative specification sections necessary to establish the phase contract. Expand context when ambiguity or a dependency requires it; do not make every specialist reread all specifications and historical contracts.

Use the bounded specialist workflow from `AGENTS.md`:

1. `@architect` performs a short contract/ownership pass and records the phase's shared decisions, public contracts, exact production/test ownership, migration/edit order, relevant normative references, and acceptance gate.
2. `@game_engine` and/or `@persistence_security` receive bounded assignments for their owned implementation only, with focused tests. They hand back and stop when their owned work is complete.
3. `@architect`/parent integrates shared application/web/presentation/docs work.
4. `@test_invariants` joins after integration for independent adversarial review/coverage, using the phase contract, final/current diff, relevant tests, and CI evidence.
5. GitHub Actions is the authoritative unchanged full-suite gate. Do not have agents rerun an already-green unchanged full suite.
6. Route failures back only to the implicated owner. Reactivate other specialists only when a concrete cross-boundary issue requires them.

This staging reduces duplicate context and repeated reasoning; it does **not** reduce specialist ownership, reasoning strength, required tests, security/isolation guarantees, concurrency verification, or the final gate.

For every phase:
- deliver working UI for newly exposed actions;
- enforce backend legality/isolation;
- use atomic persistence/audit/idempotency where applicable;
- add focused implementer tests plus independent cross-cutting tests where applicable;
- keep the simple approved Django/HTMX/SQLite architecture;
- update `USER.md`, relevant contracts/architecture, and `.env.example` when behavior/configuration changes;
- keep demonstration content clearly labeled;
- stop at the named phase gate.

## Phase 4 — puzzle-13 Music Quiz interruption

Prerequisite: phase 3.1 green. Before dependent implementation, settle the Music pause/resume and final-result-display timing contracts. Extend development data through puzzle 13 with 11 Music questions.

All three puzzle-completion routes must trigger Music immediately and exactly once. Preserve underlying team state and timer durations. Both teams answer the same active Music question. Wrong attempts are unlimited and penalty-free. The first accepted correct transaction wins the question, receives the configured normal points, and immediately advances the question. Persist Music scores separately from normal balances. After all 11 questions, show final scores for the configured duration, then restore Advent exactly. Expose only approved shared Music fields; do not leak private balances/progression. Resolve TV/audio handling before implementing playback.

Gate:
- trigger via correct answer, Skip, and admin force-completion;
- concurrent puzzle-13 completion triggers Music exactly once;
- one-time trigger marker survives retries/restart;
- underlying Freeze/timer state restores exactly;
- stale Music question IDs reject;
- all 11 questions work;
- exact configured reward, no duplicate reward/advance;
- final-results deadline survives restart and obeys the settled pause/downtime policy;
- both browsers synchronize correctly;
- deterministic real-SQLite winner tests cover A-first and B-first by controlling separate writer transactions, never sleep-based ordering.

Ready-to-paste prompt:

```text
@architect Implement only phase 4 of implementation_plan.md.

Use the bounded specialist workflow in AGENTS.md. First perform one focused contract pass: inspect the authoritative Music rules and only the supporting phase-3/3.1 contracts needed for interruption/timer restoration, then create/update a concise phase-4 contract with the Music pause/resume policy, final-result timer policy, public projection, interfaces, exact file ownership, migration/edit order, and acceptance gate.

Then delegate bounded work:
- @game_engine: only Music/interruption domain transitions, legality, scoring decisions, restoration semantics, stale-question domain behavior, and focused deterministic domain tests.
- @persistence_security: only Music persistence/schema/atomic first-winner transaction, one-time trigger/idempotency, restart durability, authorized projections, and focused persistence/security/concurrency tests.
After those handoffs, integrate application.py, views/templates/polling, demo data with 11 questions, and documentation without keeping completed specialists active.
Then invoke @test_invariants once on the integrated diff for independent race/isolation/restart/browser coverage and missing invariants.

Connect answer, Skip, and admin completion to one atomic puzzle-13 trigger. Preserve exact underlying Advent/Freeze state, use deterministic separate-SQLite-connection A-first and B-first winner tests, and let GitHub Actions run the unchanged complete gate. Route any failure only to its owner. Stop after phase 4; do not begin phase 5.
```

## Phase 5 — complete 25-puzzle progression and two-team finish

Prerequisite: phase 4 green.

Extend demonstration data to 25 puzzles per team with distinct answers and cumulative fragments referenced by puzzle 25. Enforce prerequisites. Persist the first finisher and show the winner state immediately; the other team continues and sees the specified first-finisher indication. Only both teams completing puzzle 25 makes global `FINISHED`. Finished teams cannot initiate/receive normal gameplay attacks/actions.

Gate:
- both distinct journeys run through the real Music path to 25;
- first finisher becomes inactive while the second remains playable;
- concurrent final answers yield one durable first-finisher record;
- no duplicate rewards/fragments;
- reload/restart preserves result;
- normal actions cannot reopen a finished team.

Prompt:

```text
@architect Implement only phase 5 of implementation_plan.md using AGENTS.md's bounded specialist workflow. Establish the finish/progression contract and file ownership once. Delegate pure progression/finish rules and focused tests to @game_engine; delegate durable first-finisher state, atomic final-answer race, constraints and focused persistence tests to @persistence_security. Integrate the 25-puzzle demo path/application/views yourself, then invoke @test_invariants once on the integrated diff for full-journey, finish-race and finished-team adversarial coverage. Use CI for the unchanged complete gate. Stop after phase 5.
```

## Phase 6 — Challenge normal gameplay

Prerequisite: phase 5 green; preserve the settled phase 3 Challenge-loss policy:
the Freeze applies directly to the challenged team and does not consume or
redirect an active Uno Reverse, unless a higher-authority specification conflicts.

Add one paid Challenge initiation opportunity per team and a shared Challenge puzzle. Attempts are unlimited and penalty-free; there is no deadline. First accepted correct answer wins. Challenge gives no Advent progression or normal point reward. If initiator wins, challenged team receives the specified Freeze on Advent return; if challenged team wins, resume without Freeze. Opportunity consumption and payment are atomic. Finished teams cannot participate.

Gate:
- eligibility/direct-request restrictions;
- concurrent initiations/answers;
- exactly-once opportunity and cost;
- no reward/progression;
- both outcome routes;
- pause/reconnect/restart preservation;
- disconnect never resolves Challenge.

Prompt:

```text
@architect Implement only phase 6. Settle one concise Challenge contract and bounded ownership packet first. Delegate only Challenge domain legality/outcomes to @game_engine and only durable opportunity/payment/first-winner/concurrency state to @persistence_security. Integrate application/views afterward. Invoke @test_invariants post-integration for initiation/answer races, stale/direct requests and restart coverage. Use CI for the full gate. Do not implement emergency cancellation from phase 8. Stop after phase 6.
```

## Phase 7 — usable team/admin/TV views and package authoring

Prerequisite: normal gameplay phases green; approve any extra public projection fields and TV audio workflow.

Turn functional views into usable phone/tablet team and admin interfaces: Advent calendar, shop/sabotage, fragments, distinct state screens, audit view, clear disabled/rejected actions. Keep rules on backend. Add a TV projection containing only approved public fields; never reuse team/admin private projections. Frozen screens remove private content rather than blur it. Add selected image/audio presentation and explicit operator interaction where browsers require it.

Extend phase-3.1 package discovery/selection with documented data-only authoring/import/export and richer validation for assets, validator/effect names, prerequisites, 25 puzzles per team, and 11 Music questions. Reject executable behavior. Demo content remains distinct from final authored event content.

Gate:
- expected phones/tablets/TV;
- private/public allowlists and no answer leaks;
- stable focus/input/control behavior under polling and media changes;
- keyboard/touch usability;
- package round trip and actionable invalid-package errors;
- snapshot stability after source deletion.

Prompt:

```text
@architect Implement only phase 7 using bounded assignments. Own presentation/integration and settle the public-field/audio contract once. Delegate package validation/media/security work only to @persistence_security. Involve @game_engine only if an explicit new declarative validator/rule requires domain semantics. After integration invoke @test_invariants once for privacy/public-projection and browser/polling coverage. Use CI as the full gate. Keep real event content requirements explicit and stop after phase 7.
```

## Phase 8 — explicit emergency recovery controls

Prerequisite: normal gameplay/admin gates green; settle unusual-state correction contracts first.

Add supported, explicit recovery operations rather than an unrestricted state editor: earlier-puzzle reopen/repair, finished-team reopen, team progression reset, Challenge cancellation/refund/opportunity restoration, admin Challenge initiation/resolution, admin Reverse add/remove, supported timer/effect cancellation. An earlier reopen leaves later history/rewards intact but blocks dependent progression until repaired. Historical rewards/fragments and Music trigger markers prevent duplication.

Define each operation's interaction with pauses, Music, first-finisher records, and global `FINISHED`.

Gate:
- admin permission/audit reasons;
- atomic corrections;
- no duplicate awards/fragments/Music;
- Challenge cancellation refunds/restores exactly once;
- stale commands cannot mutate corrected context;
- supported unusual-state corrections remain recoverable.

Prompt:

```text
@architect Implement only phase 8. First create one explicit emergency-operations contract defining each supported correction and its interactions with progression, historical awards, first-finisher/global state and interruptions. Delegate pure correction legality to @game_engine and atomic persistence/refund/stale-context guarantees to @persistence_security in bounded assignments. Integrate authorized admin operations, then have @test_invariants independently attack the integrated correction paths once. Use CI for the full gate. Do not add a generic state editor. Stop after phase 8.
```

## Phase 9 — backup/restore, deployment rehearsal, event readiness

Prerequisite: supported product phases green.

Deliver consistent SQLite backups together with referenced immutable snapshots, restore commands/runbook, account/package setup, restart/upgrade guidance, operator checks, and off-host backup guidance. Rehearse on disposable data and restore into a clean runtime. Validate offline static/media operation, Compose persistence/permissions, expected two-team/two-admin/one-TV load, and LAN/VPN access on actual event devices. Record measured responsiveness rather than brittle timing assertions. Trace normative requirements to tests and list gaps including missing final content.

Gate:
- fresh deployment and full-game rehearsal;
- restart during supported modes;
- consistent backup/restore preserving state/receipts/audit/media;
- all applicable automated checks green;
- operator-readable runbook;
- event readiness requires validated final package, physical/media components, and device rehearsal.

Prompt:

```text
@architect Implement only phase 9. Use one bounded deployment/recovery contract. Delegate backup/restore consistency, permissions and snapshot/database guarantees to @persistence_security. Involve @game_engine only for a confirmed domain defect. After integration invoke @test_invariants once for independent restore/isolation/browser/full-game rehearsal coverage. Use disposable runtime data for destructive checks and CI for the automated full gate. Record unavailable home-server/device checks honestly. Do not claim event readiness without final content and real-device rehearsal.
```

## Deferred decisions

First check whether authoritative rules already settle these. Record the architect's conclusion/source. Ask the user only for unresolved product choices.

| Before | Decision / constraint |
| --- | --- |
| Phase 4 Music | Supporting states permit pausing Music, while the normative diagram is not explicit. Settle whether Music can pause, what resumes, and whether final-score display duration stops during pause/downtime. Keep this timer distinct from suspended Advent gameplay timers. |
| Phase 4/7 public view | Progression/points/effects are private unless explicitly approved. Music scores and first-finisher announcement have explicit sharing rules. Approve any additional public Advent fields before exposing them. |
| Phase 4/7 audio | Choose central vs device playback workflow and define shared audio access separately from private puzzle media. |
| Phase 6 Challenge | Confirm Challenge-loss Freeze/Reverse interaction if authoritative material does not settle it. |
| Phase 8 emergency | Define earlier-puzzle repair, finished-team/global first-finisher correction, progression resets, forced Challenge resolution, and operations during interruptions. |

Already settled: Skip is immediate, Hint tokens are generic inventory, puzzle status is `completed`, Freeze hides underlying puzzle/hint content, global `FINISHED` waits for both teams, and Reset is distinct from restart.

## Validation workflow

Use disposable runtime/test data. Never mutate a live event runtime to validate a phase.

During implementation, run focused tests/checks only for the changed behavior. Rebuild application/test images when code/tests change. GitHub Actions is the authoritative clean-environment full gate for the PR and should run the complete test suite, lint, Django checks, and migration drift checks.

Do not spend specialist reasoning on rerunning an unchanged green full suite. When CI fails, inspect only the failing evidence, route it to the responsible owner, fix narrowly, run focused local verification, and let CI rerun.

Runtime/device-specific gates that CI cannot prove must still be executed at the phase that requires them or recorded honestly as unrun.

## Resume prompt for an unfinished phase

```text
@architect Resume only the unfinished phase recorded in implementation_plan.md. Read the latest phase contract/handoff, current diff/worktree, and validation/CI evidence first. Preserve completed work. Reuse @game_engine or @persistence_security only for concrete remaining owned tasks; do not reacquire all specialists by default. Invoke @test_invariants after integration only for remaining adversarial coverage. Finish the current phase gate, update docs/status, and stop. Do not restart completed work or begin the next phase.
```

## Progress summary

| Phase | Status | Evidence |
| --- | --- | --- |
| 1 | Complete | 2026-09-22; authenticated persisted vertical slice, immutable snapshots/private media, atomic completion, isolation/concurrency/recovery and browser polling coverage green. See `docs/contracts-first-slice.md` and Git history. |
| 2 | Complete | 2026-09-22; admin controls, Hint/Skip, canonical completion, atomic spending/reset/stale-request coverage green. Historical lifecycle details in `docs/phase-2-contract.md`; Reset lifecycle superseded by phase 3.1. |
| 3 | Complete | 2026-09-23; persisted gameplay clock, Freeze, Uno Reverse, protected reads, restart/pause/race/browser coverage green. See `docs/phase-3-contract.md`. |
| 3.1 | Complete | 2026-09-23; no-run READY, archival Reset, package selection/fresh snapshots, legacy READY migration, restart/snapshot/race/browser coverage green. See `docs/phase-3.1-contract.md`. |
| 4 | Not started | Next authorized phase: puzzle-13 Music Quiz; settle Music pause/result timing/public/audio decisions first. |
| 5 | Not started | 25-puzzle progression and two-team finish. |
| 6 | Not started | Challenge normal gameplay. |
| 7 | Not started | Usable team/admin/TV UI and package authoring. |
| 8 | Not started | Explicit emergency recovery controls. |
| 9 | Not started | Backup/restore, deployment rehearsal, event readiness. |
