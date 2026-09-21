# Christmas Escape Room Quiz — Codex Instructions

## Project goal

Build a lightweight, self-hosted Christmas escape-room quiz for two isolated teams, two administrators, and a public TV overview. Correctness, recoverability, team isolation, and easy game-package configuration take priority over visual polish.

## Specification authority

Read the relevant specifications before designing or changing behavior. Their authority, from highest to lowest, is:

1. `christmas-2026-game-rules-state-semantics.md` or `christmas-2026-game-rules-state-semantics(1).md` — normative game behavior and invariants.
2. `Design.md` — broader product and operational requirements.
3. `Views.md` — presentation targets and view requirements.
4. `Game States.md` — supporting state documentation.

When documents conflict, follow the higher-authority document. Do not silently invent a resolution for an ambiguity not covered by that order. Record the ambiguity and ask the user or lead architect.

Read `docs/architecture.md` for approved implementation choices and ownership before implementation. It does not override the specification authority above. The approved baseline is synchronous Django/Gunicorn WSGI, server-rendered HTMX polling, SQLite, and Docker Compose; architecture changes require architect review.

Known examples:

- Global `FINISHED` occurs only after both teams complete puzzle 25, even if an older document suggests that the first finisher ends the game.
- Skip is an immediate completion action, not stored Skip inventory, even if an older view describes purchased Skip tokens.
- Use `completed` as the canonical puzzle status. Do not create separate domain states for solved, skipped, unlocked, or finished.

## Non-negotiable architecture rules

- Implement an authoritative backend state machine. The frontend renders state and requests transitions; it never decides whether a transition is legal.
- Keep global quiz state separate from each team's activity state.
- Treat `PAUSED` and `MUSIC_QUIZ` as global interruptions that preserve underlying team states and remaining gameplay-timer durations.
- Route correct answers, player Skip actions, and admin force-completion through one canonical completion pipeline.
- Enforce strict sequential prerequisites in the backend.
- Resolve concurrent actions at an atomic persistence/transaction boundary. The first valid server-accepted transaction wins.
- Derive team identity from authenticated server context. Never trust a team ID supplied by a client to authorize team-specific reads or writes.
- Enforce team isolation on every private read and write, including progression, attempts, points, effects, hints, fragments, and puzzles.
- Keep balances non-negative and make purchases, rewards, attacks, one-time triggers, and race resolution atomic.
- Make timers server-authoritative, recoverable after refresh/reconnect/restart, and measured in Advent gameplay time where specified.
- Keep the event log immutable across a full game reset.
- Snapshot/version the active game configuration when a game starts.
- Treat `games/christmas-2026` as data, not application code. Do not allow arbitrary executable code in puzzle configuration.
- Prefer one implementation of each business rule. API handlers, UI components, and persistence adapters must call the domain/application layer rather than reimplementing policies.

## Delivery principles

- Start with a small end-to-end vertical slice: login as Team A, load Team A state, display puzzle 1, reject a wrong answer, accept a correct answer, complete atomically, award the configured reward, advance to puzzle 2, log the event, and reload the persisted result.
- Build the normal game path before low-priority emergency operations.
- Keep deployment and maintenance simple for a single home server and a developer with limited frontend experience.
- Make incremental changes and keep unrelated user changes intact.
- Add or update automated tests with every behavior change.
- Test through public domain/application interfaces where possible, not private implementation details.
- Before handing off, run the smallest relevant test suite plus the repository's required validation commands.
- Never weaken an invariant or change a specified rule merely to make a test pass.
- Do not silently change architecture, rules, or public contracts. Record meaningful decisions in the repository's architecture/decision documentation.

## Multi-agent ownership

Use the project-scoped agents in `.codex/agents/` when the user asks for multi-agent implementation:

- `architect`: architecture, shared contracts, `quiz/application.py` orchestration, sequencing, decisions, and integration review.
- `game_engine`: pure `quiz/domain/` rules, state transitions, canonical completion, and domain tests; no application orchestration or ORM.
- `persistence_security`: schema, transactions, authentication, authorization, isolation, and event persistence.
- `test_invariants`: adversarial invariant, concurrency, integration, and security verification.

Avoid concurrent edits to the same files. Establish contracts and ownership before parallel implementation. Shared contracts require architect review. Agents must inspect existing work before editing and must report overlaps or incompatible assumptions rather than overwriting another agent's changes.

The architect integrates; specialist agents do not broaden their scope just to finish an adjacent feature. A specialist may add focused tests for its own changes, while `test_invariants` owns cross-cutting and adversarial verification.

Use the ownership table in `docs/architecture.md`. The architect exclusively owns application transaction boundaries and integrates changes to shared settings, routes, dependencies, and fixtures; `persistence_security` owns storage/authentication/snapshot implementation and reviews transaction guarantees. Assign exact specialist test files and auth-view files before parallel edits. Shared domain types and migration ordering require architect coordination. Do not scaffold or start a feature merely because architecture and agent alignment are approved.

## First implementation milestone

The first milestone is complete only when the vertical slice is green and demonstrates:

- authenticated Team A access;
- rejection of Team B resource access;
- server-side answer validation;
- wrong-answer persistence without progression;
- atomic canonical completion on a correct answer;
- configurable reward application;
- sequential advancement from puzzle 1 to puzzle 2;
- immutable event recording; and
- correct state after reload.

Do not begin Freeze, Music Quiz, Challenge, Uno Reverse, or polished calendar work before this milestone is stable unless the user explicitly reprioritizes.
