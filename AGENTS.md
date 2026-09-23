# Christmas Escape Room Quiz — Codex Instructions

## Project goal

Build a lightweight, self-hosted Christmas escape-room quiz for two isolated teams, two administrators, and a public TV overview.

Correctness, recoverability, team isolation, understandable implementation, and easy game-package configuration take priority over visual polish or speculative scalability.

---

## Specification authority

Read the relevant specifications before designing or changing behavior.

Their authority, from highest to lowest, is:

1. `christmas-2026-game-rules-state-semantics.md` or `christmas-2026-game-rules-state-semantics(1).md` — normative game behavior and invariants.
2. `Design.md` — broader product and operational requirements.
3. `Views.md` — presentation targets and view requirements.
4. `Game States.md` — supporting state documentation.

When documents conflict, follow the higher-authority document.

Do not silently invent a resolution for an ambiguity not covered by that ordering. Record the ambiguity and escalate it to the `architect`; ask the user only when the ambiguity cannot safely be resolved from the approved architecture or specifications.

Read `docs/architecture.md` before implementation. It defines approved implementation choices and ownership but does not override the specification authority above.

The approved baseline is:

* synchronous Django;
* Gunicorn WSGI;
* Django templates;
* locally bundled HTMX;
* 500 ms authenticated polling;
* SQLite;
* WhiteNoise;
* Docker Compose;
* one application container;
* persistent `./var` runtime data.

Architecture changes require `architect` review.

Known examples:

* Global `FINISHED` occurs only after both teams complete puzzle 25, even if an older document suggests that the first finisher ends the game.
* Skip is an immediate completion action, not stored Skip inventory, even if an older view describes purchased Skip tokens.
* Use `completed` as the canonical puzzle status. Do not create separate domain states for solved, skipped, unlocked, or finished.

---

## Non-negotiable architecture rules

* Implement an authoritative backend state machine. The frontend renders state and requests transitions; it never decides whether a transition is legal.
* Keep global quiz state separate from each team's activity state.
* Treat `PAUSED` and `MUSIC_QUIZ` as global interruptions that preserve underlying team states and remaining gameplay-timer durations.
* Route correct answers, player Skip actions, and admin force-completion through one canonical completion pipeline.
* Enforce strict sequential prerequisites in the backend.
* Resolve concurrent actions at an atomic persistence/transaction boundary. The first valid server-accepted transaction wins.
* Derive team identity exclusively from authenticated server context. Never trust a client-supplied team ID for authorization.
* Enforce team isolation on every private read and write, including progression, attempts, points, effects, hints, fragments, inventory, puzzles, and private media.
* Keep balances non-negative and make purchases, rewards, attacks, one-time triggers, and race resolution atomic.
* Make timers server-authoritative, recoverable after refresh/reconnect/restart, and measured in Advent gameplay time where specified.
* Keep the event log append-only through supported application behavior and preserve it across a full game reset.
* Snapshot/version the active game configuration when a game starts. An active run reads only from its immutable snapshot.
* Treat `games/christmas-2026` as data, not application code. Never execute arbitrary puzzle-package code.
* Prefer one implementation of each business rule. Views and persistence code call domain/application behavior rather than reimplementing policy.
* Prefer the simplest conventional Django implementation that preserves these guarantees. Do not add abstraction layers for hypothetical future scale.

---

## Delivery principles

* Start with small end-to-end vertical slices.
* Build the normal game path before low-priority emergency operations.
* Keep deployment and maintenance simple for one home server and a developer with limited frontend experience.
* Make incremental changes and preserve unrelated user changes.
* Add or update automated tests with every behavior change.
* Test through public domain/application interfaces where practical rather than private implementation details.
* Before handing off, run the smallest relevant test suite plus required repository validation commands.
* Never weaken an invariant or change a specified rule merely to make a test pass.
* Do not silently change architecture, game rules, or public contracts.
* Record meaningful architectural decisions in the appropriate documentation.
* Do not broaden the requested implementation milestone without explicit user approval.

---

## Repository, branch, pull-request, and CI workflow

For non-trivial implementation work, the parent/main routing agent owns the Git lifecycle. Specialist agents work inside the branch/worktree assigned by the parent; they do not independently create competing branches, commits, pushes, or pull requests unless the parent explicitly delegates that responsibility.

### Branch lifecycle

When the user asks Codex to implement repository changes and does not explicitly request work directly on the current branch, first determine whether the checked-out branch already belongs to the current task or pull request. Reuse a suitable existing feature branch for follow-up work, such as review feedback or a CI fix on an open pull request. Create a new feature branch only when starting from `main` or from a branch unrelated to the requested work.

1. inspect the current Git state and preserve unrelated user changes;
2. update local knowledge of `main` and base the work on the current `main` when it is safe to do so;
3. reuse the current suitable task branch, or create a short-lived feature branch with a descriptive name such as `codex/<task>` or another repository-appropriate prefix when the current branch is `main` or unrelated;
4. perform implementation and focused local verification on that branch;
5. inspect the final diff before committing;
6. create one or more coherent commits with descriptive messages;
7. push the feature branch;
8. create a pull request targeting `main` when GitHub authentication/network access is available and the user has not asked to stop before PR creation;
9. report the branch name, pull request, local validation, and CI status in the final handoff.

Do not commit implementation work directly to `main` unless the user explicitly requests that workflow. Do not merge a pull request, enable auto-merge, alter branch protection, or delete branches unless the user explicitly asks for that action.

When multiple implementation agents truly need independent writable checkouts, the parent may use Git worktrees. Worktrees are an isolation mechanism, not a reason for each specialist to invent its own delivery branch. The parent remains responsible for integrating the final branch and PR.

### Local verification policy

Local verification is optimized for fast implementation feedback. It is not required to duplicate the full GitHub Actions suite after every edit.

During implementation:

* run the smallest tests that cover the changed behavior and nearby invariants;
* run Ruff on changed Python files or the smallest practical relevant scope;
* run Django/system/migration checks locally when the change makes those checks relevant;
* run browser tests locally when browser behavior is being changed or when they are needed to diagnose a failure;
* expand local test scope when a targeted test fails, the change is unusually broad, or the failure suggests wider impact.

Do not repeatedly run an unchanged full repository suite merely for reassurance. Expensive full browser/integration verification should normally be left to CI once focused local evidence is green.

### CI as the authoritative full-suite gate

GitHub Actions is the authoritative clean-environment verification gate for a pull request. The CI workflow is expected to build the development test image, lint Python, run Django checks, detect migration drift, and execute the complete test suite including browser tests.

A green CI run is sufficient evidence for checks that CI already executed successfully. Do not ask an agent to rerun the same unchanged full suite locally merely to reproduce green CI evidence.

When CI fails:

1. inspect the failed job/step and its logs rather than rereading all successful checks;
2. route diagnosis only to the ownership area implicated by the failure;
3. reproduce the failing check locally at the smallest useful scope when practical;
4. implement the fix and run focused local verification;
5. commit and push the correction so CI reruns;
6. avoid a blind `push → wait → guess → push` loop when the failing behavior can be exercised locally.

CI should reduce repetitive model-driven verification, not replace useful local debugging. Deterministic compute belongs in tests, Ruff, Django checks, Playwright, and GitHub Actions; model reasoning should focus on implementation, diagnosis, and gaps that deterministic checks cannot decide.

### Pull-request trigger expectations

The full CI workflow should normally run for pull requests targeting `main` and for pushes to `main`. Feature-branch pushes without a pull request should not run the expensive full CI suite unless a specific workflow requires it. This prevents duplicate push and pull-request runs for the same commit while preserving clean verification before merge and after integration on `main`.

---

# Mandatory agent routing

The project-scoped agents under `.codex/agents/` are the default owners of their respective areas.

**The user does not need to explicitly request multi-agent mode or name an agent.**

For every non-trivial implementation, debugging, or design task:

1. Inspect the task.
2. Classify it by ownership using the routing rules below.
3. Delegate work to the owning agent automatically when specialist judgment or specialist-owned edits are required.
4. Use the `architect` to coordinate tasks spanning multiple ownership areas or touching shared integration points.
5. Integrate specialist results only after their ownership boundaries and assumptions are compatible.

Verification-only and phase-gate requests follow the dedicated fast path below and do not automatically fan out to all implementation owners.

Do not perform specialist-owned implementation directly in the parent/main agent when an appropriate project agent exists, except for trivial read-only inspection, summarization, mechanical edits that do not alter behavior, or routine verification covered by the fast path below.

If implementation ownership is uncertain, route to `architect` first. A verification task is not ownership-uncertain merely because the behavior under test spans multiple components.

Do not create a new agent merely because a task spans multiple areas. Use the existing agents unless a genuinely missing responsibility is identified.

---

## Model and reasoning policy

Agent model and reasoning configuration is defined in `.codex/config.toml` and `.codex/agents/*.toml`.

Default role configuration:

* `architect`: GPT-5.6 Sol / high.
* `game_engine`: GPT-5.6 Sol / high.
* `persistence_security`: GPT-5.6 Sol / high.
* `test_invariants`: GPT-5.6 Terra / medium.
* Unconfigured subagents: GPT-5.6 Terra / medium.

These are defaults chosen according to the reasoning demands and risk of each role. Expensive high-reasoning specialists are reserved for work where their judgment materially affects correctness; routine inspection and verification should not invoke them merely because a phase is cross-cutting.

Do not escalate an agent's model or reasoning effort merely because a task is large. Escalation is appropriate when the assigned work contains genuinely difficult reasoning, unresolved architectural ambiguity, concurrency or security analysis, subtle interacting invariants, or when a previous attempt failed for reasoning-related reasons.

Do not spawn a high-effort specialist for work that is genuinely trivial and does not require its specialist judgment. Routine read-only inspection, mechanical edits, formatting, documentation cleanup, straightforward dependency updates, simple test execution, and similarly low-risk work may remain with the parent agent when they do not alter specialist-owned behavior.

Do not downgrade a specialist merely to save usage when the task falls inside the high-risk responsibilities for which that specialist is configured. In particular:

* use `architect` at high reasoning for architecture, shared contracts, integration boundaries, cross-agent conflicts, or difficult application transaction orchestration;
* use `game_engine` at high reasoning for interacting game-state rules, canonical completion, timer semantics, idempotency, race semantics, or prerequisite behavior;
* use `persistence_security` at high reasoning for authentication, authorization, team isolation, schema guarantees, atomic transactions, concurrent writes, snapshots, recovery, or security boundaries;
* `test_invariants` normally uses Terra at medium reasoning for verification; difficult concurrency/security test design, unexplained failures, or a genuinely subtle invariant may justify escalation to Sol or high reasoning.

The parent/main agent should prefer delegation based on ownership and risk, not on a desire to maximize model usage.

---

## Verification and phase-gate fast path

Verification is evidence gathering, not implementation. A phase-gate check must not automatically reproduce the implementation-time fan-out merely because the phase originally involved all specialists.

For a routine verification-only request, the parent/main agent should:

1. Read the named phase gate in `implementation_plan.md`, the current phase handoff/progress entry or phase-specific contract, and the current changed files/diff.
2. Inspect the existing relevant test commands, CI evidence, and validation evidence.
3. Run the smallest relevant local checks first.
4. If the work is on a pull request and the repository CI already provides the complete applicable gate, use the final CI run as the complete clean-environment gate rather than redundantly running the same unchanged full suite locally.
5. If CI is unavailable, does not cover a required gate, or local reproduction is needed to diagnose a failure, run the missing applicable gate locally once.
6. If all required evidence is green and no requirement is ambiguous or uncovered, report the result and stop.

Do not automatically spawn `architect`, `game_engine`, or `persistence_security` merely to watch or independently repeat green verification. Do not require each specialist to reread the whole repository or normative specification for a routine gate.

Use `test_invariants` when independent adversarial judgment is useful, when the gate contains cross-cutting concurrency/security/recovery cases that are not already convincingly exercised, or when new verification coverage must be designed. `test_invariants` should normally run on Terra / medium and should begin from the phase gate, current handoff/contract, diff, and tests rather than the full specification set.

Expand context only when evidence requires it:

* a failing domain/state-rule test may require `game_engine` and the relevant normative rule;
* a failing transaction, authorization, isolation, recovery, or persistence test may require `persistence_security` and the relevant architecture/security contract;
* an unclear shared contract, conflicting specialist assumption, integration-boundary defect, or unresolved specification interpretation may require `architect`;
* a difficult or unexplained adversarial failure may justify escalating `test_invariants` from Terra/medium to Sol and/or high reasoning.

When escalation is necessary, delegate only the failing or ambiguous ownership area. Do not automatically summon all agents for one failure.

Do not rerun an unchanged full suite merely to gain confidence. A complete gate should normally be rerun only after a relevant code/test/configuration change, after fixing a failure, when previously skipped evidence becomes available, when CI does not provide the required gate, or for final handoff when no complete CI/local gate has yet run against the final state.

An implementation prompt that names all four agents authorizes those agents for implementation ownership; it does not mean all four must participate in every later verification pass.

---

## Progress visibility and routing-agent updates

The parent/main agent is the user-facing coordinator for multi-agent work.

For any task that involves substantial investigation, multiple implementation steps, delegated agents, test/debug cycles, or work that may otherwise leave the interface showing only a generic `thinking` state for an extended period, provide concise progress updates while the work is underway.

These updates are operational summaries, not private chain-of-thought. Do not expose hidden reasoning, internal scratch work, or token-by-token deliberation. Instead, communicate the useful conclusions and actions resulting from that reasoning.

### Initial routing update

Before beginning substantial delegated work, briefly tell the user:

* what part of the requested task is being tackled;
* which specialist agent or agents are being used;
* why those agents own the work;
* whether work can safely run in parallel or must be sequenced.

For example:

> Phase 3 touches domain progression and persistence. I’m having `game_engine` inspect the rule changes while `persistence_security` checks the required schema/transaction behavior. The `architect` will reconcile their contracts before shared application code is changed.

Do not provide an elaborate plan for simple tasks.

### Updates during execution

Provide a new concise update after meaningful progress rather than remaining silent while significant work is happening.

Useful updates include:

* which specifications, architecture documents, or important code paths were inspected;
* a concrete finding that materially affects the implementation;
* which specialist is currently working on what;
* when a specialist has completed and what its important conclusion was;
* which implementation direction was selected after reconciling specialist results;
* which files or ownership areas are now being modified;
* which tests or validation commands are being run;
* a failed command, failing test, unexpected repository state, or other blocker;
* what a failure means and what approach is being tried next;
* when a previously attempted approach has been abandoned and why;
* whether remaining work is implementation, integration, verification, or cleanup.

Prefer findings over narration.

Good:

> `persistence_security` found that the current completion path reads the balance before obtaining the SQLite write transaction. That can permit a race. The fix is being kept in the application transaction boundary rather than duplicated in the domain model.

Less useful:

> I am still investigating the code.

Do not announce every file read, shell command, tool call, or trivial action. Group low-level actions into meaningful checkpoints.

### Delegated-agent visibility

When spawning a specialist, identify it by its repository role name rather than referring only to a generic background task.

Examples:

* `architect` — defining/reconciling the shared contract;
* `game_engine` — implementing or checking domain semantics;
* `persistence_security` — handling persistence, transactions, authentication, or isolation;
* `test_invariants` — independently verifying cross-cutting behavior.

When multiple agents work in parallel, keep the user aware of the workstreams without dumping their internal conversations.

For example:

> Two workstreams are active: `game_engine` is checking canonical completion semantics, while `test_invariants` is deriving the regression cases. They edit separate files, so they can proceed in parallel.

When a specialist returns, summarize its actionable result before moving on when that result materially changes the work.

### Failure and blocker reporting

Do not silently retry the same failing approach for a long period.

When an important setup command, build, test, migration, or implementation approach fails:

1. report the concrete failure;
2. state the likely implication based on available evidence;
3. state what is being changed or investigated next.

If the cause is not yet known, say so rather than inventing one.

Example:

> The Cloud setup still fails before the tests start: `uv` is trying to install the repository as a Python package, but the current `pyproject.toml` has no build-system metadata. I’m checking whether the correct fix belongs in project packaging or the Cloud setup configuration rather than repeating the same install command.

If a specialist is blocked on a contract owned by another specialist, surface that conflict and route it through `architect` rather than allowing both agents to independently invent solutions.

### Long-running work

For longer tasks, do not leave the user with only a generic `thinking` indication while several substantial steps occur.

Give a concise checkpoint whenever the phase of work materially changes, such as:

* investigation → implementation;
* specialist work → integration;
* implementation → tests;
* test failure → diagnosis;
* diagnosis → corrective implementation;
* validation → completion.

Do not manufacture updates solely to satisfy a timer. An update should contain new information.

### Final handoff

At completion, the parent/main agent must give a concise result summary containing:

* what was implemented or changed;
* the most important implementation decisions;
* specialists used, when relevant;
* files or major areas changed;
* tests and validation performed;
* failures or skipped validation, if any;
* unresolved concerns or follow-up work.

Do not report success merely because delegated agents reported success. The parent/main agent must inspect and integrate their results and verify the repository's final state.

The goal is that the user can understand what Codex is doing, why the task is progressing in a particular direction, and whether it is making progress or is blocked, without requiring access to private chain-of-thought.

---

## Agent routing table

### `architect`

Use `architect` when the task involves any of the following:

* architecture or architecture changes;
* decomposition of work spanning multiple agents;
* shared contracts or types;
* `quiz/application.py`;
* transaction orchestration across domain and persistence;
* integration between domain, persistence, authentication, views, or polling;
* shared settings or root routing;
* dependency changes;
* Docker/deployment structure;
* shared fixtures;
* migration ordering across independently developed changes;
* conflicts or ambiguity between specialist implementations;
* final integration review;
* determining ownership when routing is unclear.

The `architect` is the integration owner.

The `architect` should delegate specialist work rather than implementing all specialist concerns itself.

---

### `game_engine`

Use `game_engine` for pure game behavior, including:

* domain state transitions;
* legality rules;
* prerequisites;
* canonical puzzle completion;
* correct-answer behavior;
* Skip semantics;
* rewards as domain decisions;
* Freeze rules;
* Challenge rules;
* Music Quiz domain behavior;
* Uno Reverse domain behavior;
* timer semantics at the domain level;
* first-valid-answer race semantics;
* pure domain tests.

`game_engine` must not own:

* Django ORM implementation;
* authentication;
* authorization;
* HTTP views;
* templates;
* database transaction orchestration;
* deployment;
* application-wide integration.

If a game rule requires persistence or transaction behavior, `game_engine` defines the rule and contract, while `architect` and `persistence_security` coordinate its implementation.

---

### `persistence_security`

Use `persistence_security` for:

* Django models;
* schema design;
* migrations;
* SQLite configuration;
* database constraints;
* transaction guarantees;
* idempotency persistence;
* attempts and event persistence;
* rewards/progression persistence;
* authentication;
* authorization;
* session-derived team identity;
* team isolation;
* private-media protection;
* immutable run snapshots;
* backup/recovery persistence concerns;
* security-focused implementation tests.

`persistence_security` does not redefine game rules. It implements and enforces persistence/security requirements defined by the specifications, domain, and application layer.

Transaction boundaries shared with application orchestration require `architect` coordination.

---

### `test_invariants`

Use `test_invariants` for independent cross-cutting verification, especially:

* team-isolation tests;
* authorization bypass attempts;
* concurrency races;
* Music Quiz first-winner verification;
* duplicate/idempotent command behavior;
* stale run/question submissions;
* rollback guarantees;
* exactly-once rewards;
* restart/recovery behavior;
* snapshot stability;
* private-media isolation;
* browser-level polling races;
* HTMX poll-versus-command behavior;
* adversarial integration tests;
* recovery and backup verification.

`test_invariants` should test the contracts implemented by other agents rather than redesigning those contracts.

A specialist may add focused tests for its own code. `test_invariants` owns cross-cutting, adversarial, and integration-level invariant verification.

---

# Automatic routing examples

Apply these mappings without requiring the user to name agents.

| Requested work                                  | Required routing                                                                               |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Routine phase-gate verification                 | Parent/main agent first; `test_invariants` only when independent adversarial judgment is useful |
| Change a game rule                              | `game_engine`                                                                                  |
| Add/change a Django model                       | `persistence_security`                                                                         |
| Change authentication or team isolation         | `persistence_security`                                                                         |
| Implement a transaction spanning rules + models | `architect` coordinating `game_engine` and `persistence_security`                              |
| Implement Music Quiz winner logic               | `architect` + `game_engine` + `persistence_security`; `test_invariants` verifies race behavior |
| Add HTMX polling UI only                        | `architect` unless ownership is explicitly narrower in `docs/architecture.md`                  |
| Debug concurrent double rewards                 | `architect` coordinates `persistence_security`; `test_invariants` reproduces/verifies          |
| Add domain-only prerequisite logic              | `game_engine`                                                                                  |
| Modify Docker/Compose/dependencies/settings     | `architect`                                                                                    |
| Security review                                 | `persistence_security` + `test_invariants`                                                     |
| Cross-cutting feature                           | `architect` decomposes and delegates                                                           |
| Unclear implementation ownership                | `architect` decides                                                                            |

---

## Multi-agent execution rules

When a task spans multiple ownership areas, the `architect` must first establish:

1. the required contracts;
2. which agent owns each part;
3. shared/high-conflict files;
4. edit order where concurrent editing would be unsafe.

Parallelize only work that has non-overlapping ownership and file boundaries.

Do not allow multiple agents to concurrently edit the same shared/high-conflict file.

Agents must inspect existing repository state before editing. They must not assume another agent's work has not already changed a file.

When specialist work reveals an incompatible assumption:

* stop modifying the conflicting area;
* report the conflict to `architect`;
* resolve the contract first;
* then continue.

Do not overwrite another agent's implementation merely because a specialist prefers a different design.

---

## Shared and high-conflict integration points

The following require `architect` coordination and one assigned editor at a time:

* `quiz/application.py`;
* shared domain types;
* Django settings;
* root routes;
* project dependencies;
* `Dockerfile`;
* `compose.yaml`;
* shared fixtures;
* migration ordering;
* cross-agent public contracts;
* files explicitly identified as shared in `docs/architecture.md`.

Authentication-view files and specialist test files must have explicit ownership before parallel work.

The ownership table in `docs/architecture.md` remains authoritative for file-level ownership where it is more specific than this document.

---

## Agent completion requirements

A delegated agent must report back:

* files changed;
* contracts or assumptions relied upon;
* tests added or updated;
* validation performed;
* unresolved issues;
* any work discovered outside its ownership.

The integrating agent must inspect specialist results rather than assuming success merely because the specialist completed.

For multi-agent tasks, final integration must verify that domain, persistence, web, and tests agree on the same behavior.

---

## First implementation milestone

The first milestone is complete only when the vertical slice is green and demonstrates:

* authenticated Team A access;
* rejection of Team B resource access;
* server-side answer validation;
* wrong-answer persistence without progression;
* atomic canonical completion on a correct answer;
* configurable reward application;
* sequential advancement from puzzle 1 to puzzle 2;
* immutable/append-only event recording through supported application behavior;
* correct state after reload.

Do not begin Freeze, Music Quiz, Challenge, Uno Reverse, or polished calendar work before this milestone is stable unless the user explicitly reprioritizes.

For this milestone, expected routing is:

* `architect`: coordination, application transaction boundary, shared integration, polling/view integration;
* `game_engine`: answer/completion/progression domain behavior;
* `persistence_security`: models, migrations, transactions, authentication, authorization, isolation, snapshots/event persistence;
* `test_invariants`: cross-team isolation, rollback, concurrency, recovery, and adversarial verification.

The user should not need to repeat these agent assignments in implementation prompts.
