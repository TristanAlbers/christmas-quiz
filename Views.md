# Game Views

This document describes the required views and their presentation/interaction targets. The **2026-10-11 approved Midnight Advent redesign** in `docs/product-decisions.md` and `docs/ui/midnight-advent.md` refines the visual/layout details here while preserving all unrelated state, privacy and polling requirements. There are three main consumers:

* `administrative` — the game masters. They manage the game state, intervene when necessary, and can perform privileged controls such as point adjustments.
* `overview` — a generic public overview intended for a large shared TV. It must not expose sensitive team information such as private balances, answers, hints, or effects unless explicitly approved elsewhere.
* `team` — the participating teams. Each team has its own isolated view; Team A must never be able to reach or interfere with Team B's private state.

## Presentation is a first-class requirement

The UI is part of the product, not a final polish pass. Every phase that introduces or changes user-visible behavior must deliver a usable presentation for that behavior at the same phase gate.

The application should develop a coherent Christmas visual language incrementally: Advent-calendar doors/cards, clear game-state surfaces, festive visual accents, and deliberate visual treatment of inventory/actions. This must remain readable, responsive, and usable on the target devices; decorative styling must never reduce clarity, accessibility, touch-target quality, or privacy.

Do not reduce a specified visual state to a raw text placeholder when this document describes a graphical representation. In particular:

* where puzzle progression is shown, it should retain the Advent-calendar metaphor rather than being represented only as a percentage or text counter;
* Music Quiz progression should be immediately visible as progress through 11 questions using a progress bar or clear 11-step tracker; the public/TV overview also shows the current question number;
* active Uno Reverse and earned fragments should be recognizable visual cards/chips/badges rather than plain text prompts; the team Hint-token count belongs in the contextual Hint action rather than a separate top-level inventory card;
* Skip is an immediate action under the current game rules, so it should be presented as a styled action when available, not as stored inventory.

## Runtime language

Normal runtime presentation is Dutch-first on all three consumer surfaces. Team login/waiting/gameplay feedback, public/TV status and audio controls, and Game Master labels/controls/errors should use concise Dutch copy. Player-visible package-authored titles, questions and hints should also be Dutch where they are intended as prose.

Technical state values remain implementation details. Raw identifiers such as `READY`, `ADVENT_QUIZ`, `MUSIC_QUIZ`, `PUZZLE`, and `FREEZE` may be used by backend state, polling context, CSS/data attributes, tests, and developer documentation, but must be mapped to Dutch labels before they become normal visible UI. This requirement does not introduce a language selector or general-purpose localization framework.

## Polling and interaction stability

The application uses 500 ms HTMX polling. All views must follow `docs/polling-ui-guideline.md`.

Rapidly changing read-only state may be redrawn by the polling fragment. Controls that a user can still be interacting with must remain mounted while their semantic context is unchanged. Inputs, selects, buttons, forms, or interactive cards must not flicker, lose focus/selection, interrupt native controls, or lose clicks because a parent fragment is replaced every 500 ms.

User-visible phases should include browser regression coverage for the interaction boundaries they introduce. For polling-sensitive controls, prefer stable node/focus/caret checks and real pointer-down/poll/pointer-up behavior where practical, not only programmatic `.click()` calls.

## Admin Ready / Game Selection View

Target: `administrative`

This view is shown when no game run is active and the application is in the global `READY` condition.

It should:

* list all discoverable game packages under the configured `games/` root;
* identify each package by at least its package ID;
* show whether each package is currently valid enough to be started;
* show a concise actionable validation error for an invalid package instead of silently hiding it;
* allow an administrator to select one valid package and start a new run;
* make clear that starting creates a new game and that source-package changes do not affect an already-running game;
* keep package selectors and Start controls stable while the 500 ms status polling continues.

Viewing this page or listing/validating packages must not create immutable snapshots. A snapshot is created only when Start is accepted.

If an active run already exists, administrators must be taken to the active game administration view instead of being allowed to create a competing run.

## Team Waiting View

Target: `team`

This view is shown while no game run is active.

The team should see only a simple, visually intentional waiting state such as:

> Wachten tot de Game Master het spel start…

It must not expose the available package list, prior-run puzzle state, points, fragments, hints, effects, or other historical private state.

Once a game is started, normal polling/reload should move the team to the state belonging to the newly active run.

## Generic Puzzle Overview

Target: `overview`

This view should be optimized for desktop/TV usage and presented as the player-facing **Quizzmass** event screen rather than a technical state/status page. The normal Advent overview must not show raw backend state names such as `ADVENT_QUIZ` or use technical `Advent Quiz in progress` wording as its main identity.

It should represent:

* prominent `Quizzmass` game/event branding within the shared Christmas visual language;
* both teams' progress using two clear Advent-calendar-style progress representations (for example 25 doors/boxes per team with completed/current/future states);
* a concise progress indicator such as `13/25` and/or a percentage for each team, but not percentage text as the sole progression presentation;
* total server-authoritative playing time formatted as fixed `HH:MM:SS`, including a `00` hours field for sub-hour games and preserving existing Pause/recovery semantics;
* public winner/first-finisher information only when the game rules authorize it;
* whether each team is currently frozen during the normal Advent overview, using a clearly readable frost/ice treatment plus a textual Dutch `Bevroren` state so Freeze is not communicated by color alone.

The Freeze presentation must layer onto the team's existing Advent-calendar surface rather than replace it or obscure progression. It is driven by the authoritative effective team activity state and should enter/leave through normal 500 ms polling without depending on prior animation history. No public Freeze countdown is required or approved.

The overview should establish and reuse the shared Christmas visual language. The frozen/not-frozen boolean is the only public Freeze exception: the overview must never expose Freeze duration, cause, source/attacker, reflected-Reverse details, attack inventory, private balances/points, Hint-token counts, Uno Reverse state, fragments, submitted answers/attempts, private puzzle/hint content, private media, Challenge opportunity/inventory outside the dedicated active Challenge overview, or other hidden team effects/resources.

The dedicated Music Quiz and active Challenge takeover screens retain their separately approved content and replace the normal Advent overview while active.

## Puzzle View

Target: `team`

This view should be optimized for phone usage, with tablet compatibility.

The team Puzzle View intentionally does **not** show the persistent 25-door Advent calendar/progression grid. Overall Advent progression is shown on both the shared/general overview and the administrative view, while the team screen stays focused on the current puzzle and the resources/actions the team can use.

During normal Advent play the screen should read as a player-facing puzzle experience, not a diagnostic status page. Raw technical state chrome such as `Game: ADVENT_QUIZ`, generic `Puzzle`/state badges, and stale resolved-Challenge status must not occupy the normal puzzle hierarchy.

The current playing time remains required on the team Puzzle View. It should be a compact player-facing readout derived from the existing server-authoritative Advent gameplay clock, formatted as fixed `HH:MM:SS` and preserving Pause/recovery semantics. It must not compete visually with the point balance or reintroduce raw technical state chrome.

The normal Puzzle View should use this hierarchy:

1. a resource area with the current point balance as the strongest element;
2. compact persistent representations of earned fragments and Uno Reverse state;
3. the current puzzle content followed by the answer interaction;
4. contextual Hint and Skip actions, **side by side where width permits**, reflowing vertically on constrained phones or enlarged text without reducing their touch/readability. Both retain their contextual count/cost/legality semantics.

The Hint-token balance is deliberately **not** a standalone top-level resource card. The **Winkel** entry must be conspicuous, and an armed Reverse should be visibly recognizable as a prominent red Reverse-style card in the team's private resource area. The Hint action itself shows how many purchased Hint tokens remain, whether a Hint is legal for the current puzzle, and a clear disabled state when no token can be used. The Skip action shows its current cost and a clear disabled state when the team cannot afford it or the action is otherwise illegal. Disabled state must be understandable without relying on color alone.

Puzzle 25 is the explicit final-puzzle exception: player Skip is not available. The layout may keep the Skip position as a clearly disabled control with concise Dutch-facing explanation, but no usable Skip form/action may be exposed. Correct-answer submission remains available and administrator force completion is unaffected.

Transient outcomes and rejected-action feedback should appear near the active interaction and disappear after a short readable interval. A resolved Challenge may be surfaced briefly as feedback, but must not become permanent normal-play status chrome.

The current answer input and other still-valid controls must survive normal polling without losing focus, caret position, selection, hover/press state, or clicks. Resource-value polling may update point/fragment/Reverse display and the disabled/text state of the contextual Hint/Skip actions, but it must not recreate those action elements while their puzzle context remains unchanged.

## Freeze View

Target: `team`

This view should be optimized for phone usage.

It should use the same established visual language as the Puzzle View, but clearly communicate the frozen state with a **blue translucent animated ice layer** and the server-authoritative remaining timer. A static **non-sensitive silhouette** may suggest a puzzle underneath, but never include the actual question/media/hint markup. This is distinct from the **gold/amber global Pause** that disables all player commands while preserving the authorized underlying mode. Private underlying puzzle/hint content must not merely be blurred behind the freeze overlay; it should not be present in the rendered private content while frozen.

Nothing should be interactable from this view. When a player Freeze caused this state, the persistent ice-lock view is revealed after the corresponding transient attacked/Reverse-reflected presentation finishes; authoritative interaction restrictions apply immediately even while that presentation is still covering the page.

## Shop View

Target: `team`

This view should be optimized for phone usage.

The shop should present purchasable gameplay elements as deliberate cards/items rather than raw text controls. Depending on the current rules and eligibility it can include:

* an Uno Reverse purchase;
* Hint token purchases;
* the immediate Skip action/cost where this is exposed through the shop flow and where Skip is legal for the current puzzle.

Puzzle 25 must never expose an enabled Shop/alternate Skip entry point. Any such UI is only a convenience projection of the backend rule; stale or crafted requests remain backend-rejected.

Each offered item shows a **high-contrast server-derived cost and availability independent of its buy button**, with the once-per-team Challenge action explicitly marked **Gratis**. Costs, availability, disabled states, and rejection feedback should be visually clear. Purchasing must remain backend-authoritative. The phone overlay must have comfortable internal padding and spacing; successful shop purchases close the overlay before transient gameplay feedback starts, while rejected purchases keep it open so the rejection remains readable.

Buying Uno Reverse only arms the private Reverse indicator. The major Reverse presentation occurs later, only when an authoritative player Freeze actually triggers it. A successful Freeze purchase is presented as a major attack event rather than a quiet balance/state update.

## Sabotage View

Target: `team`

This view should be optimized for phone usage. It may be a dedicated view or a clear subview of the shop/puzzle experience.

It should contain:

* the ability to buy/send a Freeze where legal;
* Challenge initiation where legal;
* clear availability/cost/disabled/rejected states;
* no private information about the other team's inventory or state beyond explicitly approved public/interaction fields;
* player Freeze is visibly unavailable while the opponent already has an active Freeze, with the backend remaining authoritative for stale/direct attempts.

For a normal player Freeze, the attacker first sees a positive Freeze-launch animation, then the target sees a negative impact presentation before the target's persistent Freeze View is revealed. If the target had an armed Uno Reverse, the attack animation still completes first; the attacker then sees a negative reflected-Reverse presentation, the protected target sees a positive Reverse-saved presentation, and the attacker is the team that ends in the persistent Freeze View. These transient effects must play once per newly observed authoritative event and must not be inferred merely from a durable `FREEZE` or Reverse-active flag.

## Generic Music Challenge View

Target: `overview`

This view should be optimized for desktop/TV usage.

It should contain:

* an obvious progress bar or 11-step tracker showing progress through the 11 Music questions;
* the current question number;
* for an active question, a large player-style progress bar on a fixed three-minute scale, without visible endpoint time labels and without deadline semantics;
* each participating team's current Music score;
* the approved shared audio/playback interaction once that workflow is settled;
* a clearly distinct final-results state for the configured results-display duration.

Music progression should not be conveyed only as a text string such as `Question 4 of 11`; the current position must be visually scannable from across the room.

During the issue-#44 gathering subphase, the public/TV view shows a clear 60-second preparation countdown and Music scores, but no question-1 title, body, audio, or answer interaction. The countdown uses authoritative remaining Music time supplied by the server. Refresh and Pause must retain the correct remaining value. The active-question player bar is cosmetic: it does not use the audio element’s duration or playhead, and filling the fixed three-minute visual scale does not expire or advance the question. Player-facing Dutch copy uses `Muziek Quiz` as the mode name.

## Puzzle Music Challenge View

Target: `team`

This view should be optimized for phone usage.

During Music Quiz it should show only information/actions needed for that mini-game. It should contain:

* an authoritative 11-step tracker showing the current Music question;
* the team's answer field and submission action;
* concise result/rejection feedback needed for repeated attempts.

During gathering, the team view shows a concise preparation state and authoritative remaining time. It shows no question-1 details, audio, or answer controls. When question 1 becomes effective, the normal minimal Music interaction replaces that preparation state.

The team status area should not duplicate the public Music overview: it should omit a separate `Question N of 11` heading, elapsed-question timer, team Music scores, previous-winner summary, and final-results countdown. Those status details belong on the shared public/TV overview.

The answer control must remain mounted and usable across normal 500 ms polling until the authoritative question/context changes. Advancing to a new Music question is a valid context change that may replace the interaction pane.

## First-finisher / Final-result View

On a first team's completion of puzzle 25, present one-shot confetti followed by a **persistent, noninteractive winner tableau** on that team phone. The other team sees a brief, nonblocking notice and continues its puzzle with stable controls. The public TV retains both cabinets and a small first-winner marker; global `FINISHED` appears **only after the second team completes puzzle 25**, with one first winner and a positive non-winning completion state for the second team. Recovery/reload must restore durable results without replaying old celebrations. Follow the approved UI contract for visual treatment.

## Administrative View

Target: `administrative`

This view should be optimized for phone/tablet usage.

When a run is active, it should provide a user-friendly Dutch interface for the supported administrative controls described in `Design.md` and the game-state documents. It should also make team progression easy to understand at a glance. The preferred representation is two mirrored Advent calendars, one per team, with clear completed/current/future states and a concise progress marker such as `13/25`.

Admin controls must remain stable under polling; editing a number, using a native selector, pressing a command, or interacting with a form must not race against a 500 ms redraw.

When no run is active, the administrative target uses the **Admin Ready / Game Selection View** instead.

A full Reset of an active game must return administrators to the Ready / Game Selection view. A process or Docker restart must not do so when an active run is recoverable.
