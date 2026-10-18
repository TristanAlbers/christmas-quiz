# Christmas Escape Room Quiz

A self-hosted Django application for two isolated teams and two game masters.
The current app includes 25-puzzle Advent progression, a shared public TV calendar, private/team/admin views, Music Quiz, a free once-per-team Challenge with two distinct questions, Freeze/Uno Reverse effects and two-team first-finisher semantics. The **approved Midnight Advent visual redesign is planned but not yet deployed**; its parent [spec #71](https://github.com/TristanAlbers/christmas-quiz/issues/71), active [presentation contract](docs/ui/midnight-advent.md), [13-ticket backlog](docs/ui/midnight-advent-rollout.md) and [agent/skill guide](docs/ui/midnight-advent-agent-guide.md) were recorded in documentation PR #70. The redesign is a separate implementation backlog, not an already-deployed feature.

For setup and current use, read [USER.md](USER.md). For isolated validation and
container details, read [docs/scaffold.md](docs/scaffold.md). The approved
architecture is in [docs/architecture.md](docs/architecture.md), and historical phase contracts (beginning with [docs/contracts-first-slice.md](docs/contracts-first-slice.md)) remain for existing invariants rather than current task status.

The game rules are governed by
[christmas-2026-game-rules-state-semantics.md](christmas-2026-game-rules-state-semantics.md),
followed by [Design.md](Design.md), [Views.md](Views.md), and
[Game States.md](Game%20States.md). Repository work follows [AGENTS.md](AGENTS.md).

## License

Copyright © 2026 Tristan Albers.

The original Quizzmas software is **source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md)** (SPDX: `PolyForm-Noncommercial-1.0.0`). This is not an OSI-approved open-source license. Use, modification, and distribution are permitted only for purposes authorized by the license; commercial use is not generally licensed.

For commercial use, request a separate written license; see [Commercial licensing](COMMERCIAL-LICENSING.md). The required copyright notice is in [NOTICE](NOTICE).

Third-party components retain their own licenses. In particular, the locally bundled HTMX is under the Zero-Clause BSD (0BSD) license; see [vendor information](quiz/static/quiz/vendor/README.md). The PolyForm license does not relicense third-party components or assets.
