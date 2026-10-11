# Christmas Escape Room Quiz

A self-hosted Django application for two isolated teams and two game masters.
The current app includes 25-puzzle Advent progression, a shared public TV calendar, private/team/admin views, Music Quiz, a free once-per-team Challenge with two distinct questions, Freeze/Uno Reverse effects and two-team first-finisher semantics. The **approved Midnight Advent visual redesign is planned but not yet deployed**; its parent [spec #71](https://github.com/TristanAlbers/christmas-quiz/issues/71), active [presentation contract](docs/ui/midnight-advent.md), [13-ticket backlog](docs/ui/midnight-advent-rollout.md) and [agent/skill guide](docs/ui/midnight-advent-agent-guide.md) are introduced by **unmerged documentation PR #70**.

For setup and current use, read [USER.md](USER.md). For isolated validation and
container details, read [docs/scaffold.md](docs/scaffold.md). The approved
architecture is in [docs/architecture.md](docs/architecture.md), and historical phase contracts (beginning with [docs/contracts-first-slice.md](docs/contracts-first-slice.md)) remain for existing invariants rather than current task status.

The game rules are governed by
[christmas-2026-game-rules-state-semantics.md](christmas-2026-game-rules-state-semantics.md),
followed by [Design.md](Design.md), [Views.md](Views.md), and
[Game States.md](Game%20States.md). Repository work follows [AGENTS.md](AGENTS.md).
