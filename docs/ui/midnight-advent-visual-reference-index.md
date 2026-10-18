# Approved Midnight Advent — visual reference index

**User-approved on 2026-10-11:** these **three prototypes together** define the intended mood and representative interaction styling. The [binding contract](midnight-advent.md), [parent specification #71](https://github.com/TristanAlbers/christmas-quiz/issues/71), and current rules define production behavior; visual references are **not** a source of backend state, cost, timing or authentication logic.

## Approved prototype files (from the conversation's design reference pack)

| Prototype file | Key screens/behaviors approved | Related implementation tickets |
| --- | --- | --- |
| `quizzmas-midnight-v4.html` | TV paired 25-door Advent cabinets, chocolate placement (artwork superseded by the approved #101 shaped-chocolate handoff), mobile answer/resources/Hint/Skip, visible shop prices and armed red Reverse, Freeze/attack/reflection, approved Music and simplified Challenge | #73, #74, #75, #76, #81, #77, #82 |
| `quizzmas-midnight-gamemaster-v1.html` | Responsive operational Game Master READY/packages, game controls, twin cabinets, Music, Challenge, Pause, Finished | #79, #84 |
| `quizzmas-midnight-pause-victory-v1.html` | Global gold Pause over Advent/Music/Challenge/Freeze, first winner confetti+durable tableau, continuing race, final TV+phone results | #78, #83 |

Key still images present in the user-approved ZIP, for screenshot comparison:

- `quizzmas-midnight-v4-tv.png`, `quizzmas-midnight-v4-mobile.png`
- `quizzmas-midnight-v4-shop.png`, `quizzmas-midnight-v4-reverse-card.png`, `quizzmas-midnight-v4-chocolate.png`
- `quizzmas-gamemaster-v1-tablet.png`, `quizzmas-gamemaster-v1-mobile.png`
- `quizzmas-pause-victory-pause-advent-tv.png`
- `quizzmas-pause-victory-first-win-tv.png`, `quizzmas-pause-victory-first-win-mobile.png`
- `quizzmas-pause-victory-final-tv.png`

The ZIP also contains the three design/handoff Markdown notes and can be shared with an implementer as a **local reference-only file**, outside the runtime static assets.

## Accessibility and operational constraint

**The ZIP is a conversation artifact, not currently stored in the GitHub repository.** GitHub-based or cloud agents will not automatically receive it. The approved written spec is self-contained enough to guide behavior, but **literal screenshot fidelity comparison is not independently reproducible until someone makes the ZIP available in the agent's trusted local workspace or attaches it to the implementation context.**

An agent must state `visual references: available / unavailable` at start and must not fabricate screenshots, reference observations or a passed Impeccable comparison. A real screenshot of the **running Django application** is still required for visual acceptance and must be judged against this spec and, when supplied, the approved references.

Do **not** commit mock game UI code into app runtime, expose private mock data on TV, or introduce an external asset host/dependency to accommodate this archive. If storing a long-lived copy in the repository is later selected, keep it under a clearly non-runtime **design reference** directory, not public static or application templates, and keep the compressed artifact out of build/deploy packages.

## Shaped-chocolate reference update — 2026-10-18

For #102 use `quizzmas-chocolate-handoff-v1.zip` supplied in the repository root:
`references/approved-calendar-concept.png`, the approved chocolate concept sheet,
and `previews/calendar-all-open-1920x1080.png` with the actual transparent assets.
These supersede old rectangular/decorative-only chocolate references. Production
uses the original PNGs and `quiz/chocolate_manifest.json`; preview markup and
full-reveal fixtures must not be served as gameplay. Historical reference paths
are not required for this bounded integration. Live Django approval remains a
separate checkpoint.
