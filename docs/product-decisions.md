# Explicit product decisions

This file records later user-approved product decisions that intentionally refine or supersede older wording elsewhere in the repository. It overrides older specifications **only for the specific decisions stated here**. All unrelated game rules and security/privacy requirements keep their existing authority.

## 2026-09-24 — UI/interaction is a first-class requirement

User-visible behavior is not complete merely because its backend mechanics work. Every phase that adds or changes user-visible behavior must include explicit presentation/interaction acceptance criteria and a dedicated UI/interaction implementation stage unless the contract demonstrates that no UI change is required.

The UI should develop a coherent Christmas visual language incrementally instead of deferring presentation until a late polish phase. Required visual semantics must not be replaced by raw text placeholders when the view specification calls for a visual representation.

Polling stability is part of correctness. Under the 500 ms HTMX polling architecture, controls that remain semantically valid must not be recreated in a way that loses focus, caret, native selection, hover/press state, touch interaction, or clicks. Browser regression coverage should exercise these interaction boundaries where relevant.

## 2026-09-24 — team Puzzle View stays focused on the current puzzle

The team Puzzle View intentionally does **not** render the persistent 25-door Advent progression grid. The Advent-calendar metaphor remains required wherever overall puzzle progression is presented: the shared public/TV overview and the administrative view both show the two teams' progression. On the team phone/tablet, the current puzzle is the active event/door experience without a separate persistent progression surface.

The team view groups its resource and status controls above the current-puzzle interaction, with the answer field below that resource area. This keeps the current puzzle and its usable actions prominent on a phone while avoiding a large duplicate overview.

This is a presentation decision only. Each team's independent sequential progression remains backend-authoritative, the authenticated team projection may retain its own progress data for state coordination, and all isolation, completion, recovery, and polling-stability requirements remain unchanged.

## 2026-09-24 — public Advent progression is approved

The shared public/TV overview may expose **coarse Advent progression for both teams** so viewers can follow the race. The approved public progression fields are limited to information needed to render the progression metaphor, such as:

- completed/current/future status for the 25 Advent doors/boxes;
- a concise progress count such as `13/25` or equivalent percentage;
- first-finisher / final-result information when already allowed by the game rules.

This is a deliberate exception to older wording that treated all team progression as private. It does **not** authorize exposing private puzzle content, answers, answer attempts, balances/coins, fragments, hints, Hint inventory, Uno Reverse state, Freeze/other hidden effects, private media, or other team-private data.

The public overview should present this progress using the Advent-calendar metaphor; percentage/count text alone is not sufficient.

## 2026-09-24 — specific visual requirements

The following are binding presentation requirements:

- Music Quiz progression is visually obvious across all 11 questions using a progress bar or clear step tracker in addition to the question number.
- Active Uno Reverse and available Hint tokens use deliberate visual card/token/badge treatment rather than raw text prompts.
- Skip remains an immediate completion action and should be presented as a styled action when available, not as stored inventory.
- Team/admin views target phone/tablet use; the shared overview targets desktop/TV use.

These decisions change presentation and approved public projection only. They do not change backend game legality, atomicity, team isolation for private data, or the authoritative state-machine rules.

## 2026-09-24 — team Music Quiz status is intentionally minimal

During the Music Quiz, team phone views should keep only the interaction and progress information needed to answer the active question:

- keep the existing 1–11 visual question tracker;
- keep the existing answer field and submission interaction;
- keep concise answer/result feedback needed for repeated attempts;
- do **not** show a separate `Question N of 11` status heading, elapsed-seconds counter, either team's Music score, previous-winner summary, or final-results countdown in the team status area.

The shared public/TV Music overview remains the place for the full question-number, timer, score, winner, and final-results status presentation. This specifically refines the earlier Music visual requirement: the phrase "in addition to the question number" applies to the public/TV overview, while the team phone view may use the 11-step tracker by itself for question progress.

This is presentation-only. It does not change Music Quiz state, scoring, answer legality, progression, polling architecture, or backend projections.
