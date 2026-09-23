# Game Views

This document is here to describe the different game views and they targets. There are three main consumers of these views, which will be hence refered to as targets:
* `adminstrative` - These are the game masters. Their role is to manage the game state and intervene if nessecary. They also hold the privilege of adding extra points to teams if needed.
* `overview` - This target is a generic overview. This could be seen by any one and should hence not expose any sensitive info (like currency points per team).
* `team` - These are the participating teams in the game. They are most interested in specific info needed to play the game. Note that each team would need its own "instance", as in team A should not be able to reach or interfere with team B's view.

## Admin Ready / Game Selection View

Target: `administrators`

This view is shown when no game run is active and the application is in the global `READY` condition.

It should:

* list all discoverable game packages under the configured `games/` root;
* identify each package by at least its package ID;
* show whether the package is currently valid enough to be started;
* show a concise actionable validation error for an invalid package instead of silently hiding it;
* allow an administrator to select one valid package and start a new run;
* make clear that starting creates a new game and that source-package changes do not affect an already-running game.

Viewing this page or listing/validating packages must not create immutable snapshots. A snapshot is created only when Start is accepted.

If an active run already exists, administrators must be taken to the active game administration view instead of being allowed to create a competing run.

## Team Waiting View

Target: `team`

This view is shown while no game run is active.

The team should see only a simple waiting state such as:

> Waiting for the game master to start a game…

It must not expose the available package list, prior-run puzzle state, points, fragments, hints, effects, or other historical private state.

Once a game is started, normal polling/reload should move the team to the state belonging to the newly active run.

## Generic Puzzle Overview

Target: `overview`

This view should be optimized for desktop usage, we will stream this view to a large TV that all teams are able to see.

This view should represent:
* The current progress in percentage of both teams
* The total playing time

## Puzzle view
Target: `team`

This view should be optimized for phone usage, since the team will be connecting to it via mobile phones.

It should represent:
* The event boxes needed for the puzzle
* Current playing time
* A image to see if an Uno Reverse card has been purchased and is active or not.
* An image to see if and how many skips have been bought and are still active. (already used skips are not relevant)
* An image to see if and how many hints have been bought and are still active. (already used hints are not relevant)
* Total amount of coins / points
* Possible interactions with the event boxes to get new questions
* Possible interactions with the event boxes to get a hint by using a previously bought hint from the shop.
* Possible interactions with the event boxes to submit answers to the questions
* Possible interactions with the event boxes to use a previously bought skip.
* Possible interactions to open a **Shop View**
* Possible interactions to open a **Sabotage View**

## Freeze View
Target: `team`

This view should be optimized for phone usage, since the team will be connecting to it via mobile phones.

It should closely mirror the **Puzzle View**, but with a frozen hue over it and a timer of 5 minutes that is counting down.
Nothing should be interactable from this view.

## Shop View

Target: `team`

This view should be optimized for phone usage, since the team will be connecting to it via mobile phones.

It should represent a shop where you can buy:
* Uno Reverse cards
* Skip tokens for questions
* Hint tokens for questions

## Sabotage View

Target: `team`

This view should be optimized for phone usage, since the team will be connecting to it via mobile phones.

It should represent a place where sabotage actions can take place. This might be a smaller sub view inside either the shop or the puzzle view. It should contain:
* The ability to buy a freeze
* The ability to send a bought freeze to the enemy team
* The ability to challenge the enemy team (logic for challenge describe elsewhere in Design and Game States)

## Generic Music Challenge View
Target: `overview`

This view should be optimized for desktop usage, we will stream this view to a large TV that all teams are able to see.

It should contain the current game state of the music challenge. Meaning the number of the current question (there are 11 in total), and a timer per question that starts from 0 and counts up. From this view we might possibly play the music needed to answer the question later. We could also manual play this from our phones, to be decided.

It should also show for each participating team their current score.

## Puzzle Music Challenge View

Target: `team`

This view should be optimized for phone usage, since the team will be connecting to it via mobile phones.

This view should reflect the current state of the music challenge and only information needed for this challenge since all other interactions are disabled. Essentially this would boil down to the question number, this should correspond with the generic music challenge view, and a field where the team can submit their answer.

## Administrative View

Target: `administrators`

This view should be optimized for phone usage, since the admins will be connecting to it via mobile phones.

When a run is active, it should essentially be a user friendly interface of the things described in [Administrative Controls](./Design.md#administrative-controls) in the Game State document.

When no run is active, the administrative target uses the **Admin Ready / Game Selection View** instead.

A full Reset of an active game must return the administrators to the Ready / Game Selection view. A process or Docker restart must not do so when an active run is recoverable.
