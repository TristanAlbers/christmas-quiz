# Explicit product decisions

This file records later user-approved product decisions that intentionally refine or supersede older wording elsewhere in the repository. It overrides older specifications **only for the specific decisions stated here**. All unrelated game rules and security/privacy requirements keep their existing authority.

## 2026-09-24 — UI/interaction is a first-class requirement

User-visible behavior is not complete merely because its backend mechanics work. Every phase that adds or changes user-visible behavior must include explicit presentation/interaction acceptance criteria and a dedicated UI/interaction implementation stage unless the contract demonstrates that no UI change is required.

The UI should develop a coherent Christmas visual language incrementally instead of deferring presentation until a late polish phase. Required visual semantics must not be replaced by raw text placeholders when the view specification calls for a visual representation.

Polling stability is part of correctness. Under the 500 ms HTMX polling architecture, controls that remain semantically valid must not be recreated in a way that loses focus, caret, native selection, hover/press state, touch interaction, or clicks. Browser regression coverage should exercise these interaction boundaries where relevant.

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
