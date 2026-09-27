# Game Views

This document describes the required views and their presentation/interaction targets. There are three main consumers:

* `administrative` — the game masters. They manage the game state, intervene when necessary, and can perform privileged controls such as point adjustments.
* `overview` — a generic public overview intended for a large shared TV. It must not expose sensitive team information such as private balances, answers, hints, or effects unless explicitly approved elsewhere.
* `team` — the participating teams. Each team has its own isolated view; Team A must never be able to reach or interfere with Team B's private state.

## Presentation is a first-class requirement

The UI is part of the product, not a final polish pass. Every phase that introduces or changes user-visible behavior must deliver a usable presentation for that behavior at the same phase gate.

The application should develop a coherent Christmas visual language incrementally: Advent-calendar doors/cards, clear game-state surfaces, festive visual accents, and deliberate visual treatment of inventory/actions. This must remain readable, responsive, and usable on the target devices; decorative styling must never reduce clarity, accessibility, touch-target quality, or privacy.

Do not reduce a specified visual state to a raw text placeholder when this document describes a graphical representation. In particular:

* where puzzle progression is shown, it should retain the Advent-calendar metaphor rather than being represented only as a percentage or text counter;
* Music Quiz progression should be immediately visible as progress through 11 questions using a progress bar or clear 11-step tracker; the public/TV overview also shows the current question number;
* active Uno Reverse and available Hint tokens should be recognizable visual cards/tokens/badges rather than plain text prompts;
* Skip is an immediate action under the current game rules, so it should be presented as a styled action when available, not as stored inventory.

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

> Waiting for the game master to start a game…

It must not expose the available package list, prior-run puzzle state, points, fragments, hints, effects, or other historical private state.

Once a game is started, normal polling/reload should move the team to the state belonging to the newly active run.

## Generic Puzzle Overview

Target: `overview`

This view should be optimized for desktop/TV usage.

It should represent:

* both teams' progress using two clear Advent-calendar-style progress representations (for example 25 doors/boxes per team with completed/current/future states);
* a concise progress indicator such as `13/25` and/or a percentage for each team, but not percentage text as the sole progression presentation;
* total playing time;
* public winner/first-finisher information only when the game rules authorize it.

The overview should establish and reuse the shared Christmas visual language. It must never expose private balances, hints, answers, fragments, or hidden effects.

## Puzzle View

Target: `team`

This view should be optimized for phone usage, with tablet compatibility.

The team Puzzle View intentionally does **not** show the persistent 25-door Advent calendar/progression grid. Overall Advent progression is shown on both the shared/general overview and the administrative view, while the team screen stays focused on the current puzzle and the resources/actions the team can use.

It should represent:

* current playing time;
* an intentional graphical/card/badge representation of whether an Uno Reverse is active;
* an intentional graphical/card/badge representation of the number of available Hint tokens;
* total amount of coins/points;
* puzzle content/media needed by the current event box;
* interactions with the current event box to reveal/use a purchased hint where legal;
* answer submission for the current question;
* a clearly styled immediate Skip action where legal under the current rules;
* access to a **Shop View**;
* access to a **Sabotage View**.

Puzzle 25 is the explicit final-puzzle exception: player Skip is not available. The layout may keep the Skip position as a clearly disabled control with concise Dutch-facing explanation, but no usable Skip form/action may be exposed. Correct-answer submission remains available and administrator force completion is unaffected.

The team resource/status controls should be grouped above the current puzzle interaction so the answer field sits below that resource area and remains prominent on a phone.

The current answer input and other controls must survive normal polling without losing focus, caret position, selection, hover/press state, or clicks.

## Freeze View

Target: `team`

This view should be optimized for phone usage.

It should use the same established visual language as the Puzzle View, but clearly communicate the frozen state and the remaining timer. Private underlying puzzle/hint content must not merely be blurred behind the freeze overlay; it should not be present in the rendered private content while frozen.

Nothing should be interactable from this view. When a player Freeze caused this state, the persistent ice-lock view is revealed after the corresponding transient attacked/Reverse-reflected presentation finishes; authoritative interaction restrictions apply immediately even while that presentation is still covering the page.

## Shop View

Target: `team`

This view should be optimized for phone usage.

The shop should present purchasable gameplay elements as deliberate cards/items rather than raw text controls. Depending on the current rules and eligibility it can include:

* an Uno Reverse purchase;
* Hint token purchases;
* the immediate Skip action/cost where this is exposed through the shop flow and where Skip is legal for the current puzzle.

Puzzle 25 must never expose an enabled Shop/alternate Skip entry point. Any such UI is only a convenience projection of the backend rule; stale or crafted requests remain backend-rejected.

Costs, availability, disabled states, and rejection feedback should be visually clear. Purchasing must remain backend-authoritative. The phone overlay must have comfortable internal padding and spacing; successful shop purchases close the overlay before transient gameplay feedback starts, while rejected purchases keep it open so the rejection remains readable.

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

## Administrative View

Target: `administrative`

This view should be optimized for phone/tablet usage.

When a run is active, it should provide a user-friendly interface for the supported administrative controls described in `Design.md` and the game-state documents. It should also make team progression easy to understand at a glance. The preferred representation is two mirrored Advent calendars, one per team, with clear completed/current/future states and a concise progress marker such as `13/25`.

Admin controls must remain stable under polling; editing a number, using a native selector, pressing a command, or interacting with a form must not race against a 500 ms redraw.

When no run is active, the administrative target uses the **Admin Ready / Game Selection View** instead.

A full Reset of an active game must return administrators to the Ready / Game Selection view. A process or Docker restart must not do so when an active run is recoverable.
