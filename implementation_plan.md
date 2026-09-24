# Christmas quiz implementation plan

Status: phases 1–4 are complete and validated as of 2026-09-24. Phases 5–9 remain plans. This file never authorizes work by itself; the user authorizes one named stage of one named phase.

Historical behavior/evidence for completed phases lives in the phase contracts, architecture docs, `USER.md`, Git history, and CI. Do not reread completed-phase history unless the current stage depends on it.

## Current baseline

Phases 1–4 provide:
- Django/Gunicorn, templates + local HTMX, SQLite, WhiteNoise and Compose;
- isolated team/admin authentication and protected private media;
- immutable package snapshots, receipts/audit, WAL/IMMEDIATE transaction behavior;
- 500 ms polling with stable-interaction architecture;
- admin controls, Hint/Skip, Freeze, Uno Reverse, persisted timers/recovery;
- READY/package selection/archival Reset lifecycle;
- one-time puzzle-13 Music interruption with 11 shared questions, rewards/scores, pause/recovery/final-results timing, synchronized team/admin/TV views and current-audio isolation;
- domain/integration/security/Chromium coverage for implemented behavior.

Phase 4 is complete and MUST NOT be reimplemented. See `docs/phase-4-contract.md` and PR #6.

## Active UI debt

Completed backend phases still leave presentation debt. Retire it incrementally, beginning with Phase 5 unless a separate UI-only repair is explicitly authorized:
- coherent reusable Christmas shell/visual language;
- Advent-calendar progression on the admin and public/TV surfaces rather than text/percentage alone;
- prominent 11-step Music progress;
- visual Hint-token and Uno-Reverse treatment;
- styled immediate Skip;
- polling-safe input/select/button/card interaction.

`docs/product-decisions.md` records the approved coarse public Advent-progression boundary.

## How to run a stage

The global stage sequence, models, ownership, STOP rule, context discipline, progress reporting and validation policy are defined in `AGENTS.md` and the selected role TOML. Do not repeat them in prompts.

Use this invocation pattern:

```text
@<role> Execute only Phase <N> Stage <letter> from implementation_plan.md.
Follow AGENTS.md and your role configuration. Use the current phase contract/handoffs
and only the authority needed for this packet. Report the handoff and STOP.
```

Stage letters:
- A `architect` — contract/boundaries/acceptance.
- B `game_engine` — domain. Use `game_engine_high` only for a separately authorized concrete escalation.
- C `persistence_security` — persistence/security/concurrency.
- D `integrator` — application/projections/routes/HTMX/data/docs.
- E `ui_experience` — presentation/interaction/browser behavior.
- F `test_invariants` — independent review-first verification.

Skip a stage only when its phase packet/contract explicitly says there is no owned work. User-visible phases require Stage E unless the contract proves no presentation/interaction change is required. GitHub Actions runs after Stage F as the complete deterministic gate. Repair failures in a new turn owned only by the implicated role.

## Phase 5 — complete 25-puzzle progression and two-team finish

Prerequisite: Phase 4 green.

Goal: extend demo data to 25 puzzles per team, preserve strict prerequisites, support cumulative fragments/final puzzle, persist the first finisher, keep the second team playable, and enter global `FINISHED` only after both teams complete puzzle 25.

UI acceptance:
- admin/public progression uses Advent-calendar completed/current/future states;
- the team Puzzle View omits the persistent 25-door grid and keeps resources/status above the current puzzle and answer interaction;
- concise `N/25`/percentage may supplement, never replace, the Advent representation;
- first-finisher/finished states are obvious without private-state leakage;
- inherited UI debt above is retired on affected surfaces.

Gate:
- both distinct journeys traverse the real Music path to 25;
- first finisher becomes inactive while the other team remains playable;
- concurrent final answers produce one durable first-finisher record;
- no duplicate rewards/fragments; restart/reload preserves outcome;
- finished teams cannot resume normal actions;
- phone/tablet/TV puzzle, progression, and finish UI is polling-stable;
- inherited UI debt is retired or explicitly deferred with separate user approval.

Stage packets:
- **A — architect:** settle first-finisher/global FINISHED semantics, legality, atomic race expectation, approved team/admin/public projections, UI/polling contract, ownership/edit order and gate.
- **B — game_engine:** implement pure progression/finish rules and focused deterministic tests.
- **C — persistence_security:** implement durable first-finisher state, atomic final-answer race, constraints/recovery/idempotency, and support only the approved coarse public progression.
- **D — integrator:** wire 25-puzzle application journeys, projections, stable HTMX boundaries, demo data/docs and focused integration tests; never expose private puzzle content/balances/hints/inventory/fragments/hidden effects publicly.
- **E — ui_experience:** implement Advent-calendar admin/public progression, a focused team current-puzzle layout, finished states, responsive Christmas presentation, Music 11-step tracker, visual Hint/Reverse, styled Skip and polling-safe interactions with focused browser tests.
- **F — test_invariants:** review full journey, finish race, duplicate effects, recovery, finished-team legality, public/privacy boundary, inherited UI acceptance and polling/browser gaps.

## Phase 6 — Challenge normal gameplay

Prerequisite: Phase 5 green. Preserve the settled Phase-3 Challenge-loss Freeze/Reverse policy unless higher authority conflicts.

Goal: one paid Challenge opportunity per team; shared Challenge puzzle; unlimited penalty-free attempts; first server-accepted correct answer wins; no Advent progression/reward; initiator win freezes challenged team on Advent return; challenged-team win resumes without Freeze; initiation cost/opportunity are atomic; finished teams cannot participate.

Gate:
- eligibility/direct-request restrictions;
- atomic initiation/answer races and exactly-once opportunity/cost;
- both outcomes, no reward/progression;
- pause/reconnect/restart preservation; disconnect never resolves Challenge;
- Challenge/Sabotage UI clearly shows state/cost/eligibility/rejection and remains polling-stable.

Stage packets:
- **A — architect:** settle Challenge legality/outcomes, Freeze/Reverse interpretation, transaction/projection/UI contracts, ownership and gate.
- **B — game_engine:** implement eligibility/transitions/first-answer outcomes/no-reward/return effects with focused tests.
- **C — persistence_security:** implement durable opportunity/payment, atomic initiation/first-winner, exactly-once handling, restart durability and authorization/isolation.
- **D — integrator:** wire Challenge application/projections/routes/stable HTMX boundaries/docs and focused integration tests; do not implement Phase-8 emergency cancellation.
- **E — ui_experience:** implement distinct Challenge/Sabotage presentation, cost/eligibility/disabled/rejected states, stable answer/action controls and responsive Christmas UI.
- **F — test_invariants:** review races, stale/direct requests, payment/opportunity exactly-once behavior, pause/restart/disconnect, finished-team restrictions, privacy and polling/UI requirements.

## Phase 7 — complete team/admin/TV usability and package authoring

Prerequisite: normal gameplay phases green.

Goal: consolidate/refine the already-started UI; complete phone/tablet team/admin experience, TV overview, media, fragments/audit/shop/sabotage, package authoring/import/export, validation UX, keyboard/touch usability and one coherent design system.

Gate:
- representative phone/tablet/TV layouts are usable;
- all `Views.md` requirements are implemented or explicitly deferred with user approval;
- public progression follows `docs/product-decisions.md`; no private/answer leakage;
- focus/input/select/button behavior remains stable under polling/media updates;
- keyboard/touch usability;
- coherent Advent/Christmas visual system;
- package round trip/actionable errors and snapshot stability after source deletion.

Stage packets:
- **A — architect:** produce remaining Views.md gap list, public/private projection/media contract, polling boundaries, package-security/UI ownership and gate.
- **B — game_engine (conditional):** only if a new declarative validator/rule has real domain semantics; otherwise report intentionally skipped.
- **C — persistence_security:** implement assigned package validation/media/security/snapshot work and focused tests.
- **D — integrator:** implement remaining projection/media/package-authoring integration, stable HTMX boundaries/docs and focused integration tests.
- **E — ui_experience:** complete/refine team/admin/TV, admin/public Advent calendars, the focused team puzzle layout, shop/sabotage, fragments/audit, media/operator interaction, disabled/rejected states, package-authoring UX, keyboard/touch and polling browser regressions.
- **F — test_invariants:** review Views/product-decision traceability, leakage, polling/media races, keyboard/touch, package round-trip/validation and snapshot stability.

## Phase 8 — explicit emergency recovery controls

Prerequisite: normal gameplay/admin gates green.

Goal: supported explicit recovery operations rather than a generic state editor: earlier-puzzle repair, finished-team reopen, progression reset, Challenge cancellation/refund/opportunity restoration, admin Challenge initiation/resolution, Reverse add/remove and supported timer/effect cancellation. Preserve audit/history and duplicate-prevention guarantees.

Gate:
- admin authorization/audit reasons and atomic corrections;
- no duplicate awards/fragments/Music;
- cancellation refunds/restores exactly once;
- stale commands cannot mutate corrected context;
- unusual-state corrections remain recoverable;
- dangerous controls are grouped, clear, appropriately confirmed/reasoned and polling-stable.

Stage packets:
- **A — architect:** settle correction semantics/interactions, authorization/audit, projections, dangerous-action UI, ownership and gate.
- **B — game_engine:** implement pure correction legality/state transitions with focused tests.
- **C — persistence_security:** implement atomic correction/refund/restoration/stale-context/audit guarantees and focused persistence/security/concurrency tests.
- **D — integrator:** wire authorized admin commands/projections/routes/stable HTMX boundaries/docs; never add a generic state editor.
- **E — ui_experience:** implement grouped dangerous-action UX, reason/confirmation flows where required, outcome/rejection feedback and phone/tablet polling stability.
- **F — test_invariants:** review permissions/audit, exactly-once restoration/refunds, duplicate prevention, stale commands, interruption interactions, recovery and dangerous-action UI behavior.

## Phase 9 — backup/restore, deployment rehearsal, event readiness

Prerequisite: supported product phases green.

Goal: consistent SQLite + immutable snapshot/media backups, restore commands/runbook, account/package setup, restart/upgrade guidance, off-host backup guidance, disposable rehearsal, offline static/media operation, Compose persistence/permissions, expected load, and actual-device LAN/VPN rehearsal where available.

Gate:
- fresh deployment/full-game rehearsal and restart in supported modes;
- consistent backup/restore preserving state/receipts/audit/media;
- all applicable automated checks green;
- operator-readable runbook;
- final package/physical-media/device rehearsal completed before claiming event readiness.

Stage packets:
- **A — architect:** settle backup consistency boundary, snapshot/media set, restore/rehearsal scope, ownership, unavailable real-device checks and remaining device/UI acceptance.
- **B — game_engine (normally skipped):** only for a concrete domain defect found by rehearsal; otherwise report intentionally skipped.
- **C — persistence_security:** implement backup/restore consistency, permissions, database/snapshot/media guarantees and focused recovery tests/runbook support using disposable data.
- **D — integrator:** implement deployment/runbook/account/package setup, Compose/static/media/operator guidance, disposable rehearsal tooling and measurable readiness checks; record unavailable real-device checks honestly.
- **E — ui_experience:** review/fix presentation/interaction defects on representative phone/tablet/TV sizes and confirm bundled/offline Christmas assets; record unavailable hardware checks honestly.
- **F — test_invariants:** review restore consistency, isolation, restart behavior, requirements/UI gaps and rehearsal evidence; add only concrete missing automated cases.

## Deferred decisions

Check authority and `docs/product-decisions.md` first. Ask the user only for unresolved choices:
- Phase 6: Challenge-loss Freeze/Reverse interaction if authority does not settle it.
- Phase 8: exact earlier-puzzle/finished-team/global correction and forced-Challenge behavior.
- Phase 7/9: only richer final-event media/operator behavior beyond the settled Phase-4 TV Music/current-audio contract.

Already settled include immediate Skip, generic Hint inventory, `completed` status, Freeze privacy, two-team global finish, Reset vs restart, Phase-4 Music timing/audio semantics, coarse public Advent progression, and UI/polling requirements.

## Resume unfinished work

Do not restart a phase. Inspect its latest contract/handoff/diff/CI evidence, identify exactly one unfinished stage and run only that stage with the generic invocation above.

## Progress summary

| Phase | Status |
| --- | --- |
| 1 | Complete — authenticated persisted slice, snapshots/private media, atomic completion, isolation/concurrency/recovery/browser coverage. |
| 2 | Complete — admin controls, Hint/Skip, canonical completion, atomic spending/reset/stale handling. |
| 3 | Complete — gameplay clock, Freeze, Uno Reverse, protected reads, restart/pause/race/browser coverage. |
| 3.1 | Complete — READY lifecycle, archival Reset, package selection/snapshots, legacy migration, recovery/browser coverage. |
| 4 | Complete — Music trigger/questions/rewards/timing/recovery/team-admin-TV synchronization/audio isolation; full Phase-4 validation and CI green. |
| 5 | Not started — 25-puzzle progression/two-team finish + Advent/public progression + inherited UI debt. |
| 6 | Not started — Challenge gameplay + Challenge/Sabotage UI. |
| 7 | Not started — UI consolidation + media/package authoring. |
| 8 | Not started — emergency recovery controls + intentional admin UX. |
| 9 | Not started — backup/restore/deployment/device rehearsal/event readiness. |
