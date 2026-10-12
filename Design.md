# Christmas Escape Room Quiz

> **Current authority and UI status (2026-10-11):** This is the original product narrative, not a current feature/phase checklist. The later explicit decisions in `docs/product-decisions.md` supersede conflicting older narrative where stated (for example **Challenge is free, has two distinct initiating-team puzzles and a 30-second gathering period; player Skip is forbidden on puzzle 25; Music has a 60-second gathering period; global FINISHED requires both teams to finish**). The approved visual implementation follows `docs/ui/midnight-advent.md` and GitHub spec #71. **Do not infer new game rules from old examples below.**

During the Christmas evening we would like to host a quiz / escape room game where multiple participants are split into two groups and these two groups will race to finish all the quizzes as soon as possible. The group that first finishes all the quizzes wins. There will also be two admins keeping everything in check.

## Participants, Setup and Context

There will be two groups participating in the game. The size will be roughly 5 persons per group, ages will vary from 16 to 57. Both groups will receive an electronic device (either a phone or tablet, to be decided later) that will be configured with a VPN to reach our home network where we have a small server running. Meaning that the application made can be self hosted and easily accessed. The same holds for the devices of the admins, they will also be equipped with a VPN to tunnel back to the home network.

The application must treat the two teams as completely isolated game sessions. A team must never be able to access, navigate to, or otherwise interact with the other team's game state, even if they attempt to manually manipulate URLs, API requests, or frontend state. Team-specific authorization and validation must therefore be enforced by the backend, not merely by hiding elements in the frontend.

For example, Team A should not be able to navigate from:

`/team/a`

to:

`/team/b`

and gain access to Team B's state. The backend must reject such requests regardless of how they are made.

The same principle applies to puzzle answers, progression, points, active effects, hints, shields, collected puzzle fragments, and any other team-specific information.

## Main Game Loop

Overall puzzle progression should use an Advent calendar with dates from 1 to 25 on the shared public/TV overview and administrative view. The team Puzzle View instead concentrates on the current event/door and intentionally does not render the persistent 25-door progression grid. Starting at 1, the current event should present its question. How the puzzles look exactly will be discussed later, but it is important to note that this could also be a hint or a sound; it does not only need to be text. There should also be an option to submit an answer.

The type of answer is fully dependent on the quiz question. This could be a number, but could also be a string or another appropriate format.

When the correct answer is submitted by the players, the next event/door becomes current and its question appears. The overview and administrative Advent calendars should reflect that progression.

Each team should have its own independent progression through the 25 puzzles. Team A solving a puzzle has no effect on Team B's progression through its own puzzles.

The application should maintain the state of each team independently, including:

* Current puzzle
* Completed puzzles
* Answer attempts
* Points
* Active effects
* Timers
* Purchased hints
* Uno Reverses
* Collected puzzle fragments
* Any other relevant game state

The admins will need a view where the progression of both teams is displayed. One visually pleasing option here is that two advent calendars, one for each team, are displayed. These should actively mirror the current state of calendars of the teams. A progression bar could also be displayed on top, showing for example `1/25`.

The admin view should update in real time or near-real time so that the admins can monitor the game without having to manually refresh the page.

## Puzzles

The puzzles will be varied. Each team will have the same "types" of puzzles to ensure fairness, but they will never have similar answers as to limit cheating.

When the boxes open they can be either questions in text, sounds, visual images, or a combination of the aforementioned options. As mentioned before, the form of the answers can also differ depending on the question.

We will define each specific puzzle by hand later, but for the architectural design this must be kept in mind.

Some puzzles will also have a physical element. We will provide these elements, but it can happen that a question gives a piece of information and points to a physical puzzle, whereafter the participants can combine that information to produce an answer and submit it to the current advent calendar box.

Ideally we would like all these "smaller" questions to give pieces of a larger puzzle, which will be puzzle 25. Puzzle 25 should only be solvable after all the individual puzzles have been solved.

Puzzle 25 should therefore be capable of using information collected from previous puzzles. Individual puzzles may provide fragments, numbers, symbols, words, codes, or other pieces of information which are stored as part of the team's progression and later used by the final puzzle.

The final puzzle should not simply be another independent question. It should be possible for the puzzle system to reference information obtained from earlier puzzles.

### Puzzle Content vs Application Code

The specific Christmas puzzles should be treated as **data rather than application code**.

The application itself should provide the generic functionality required to display puzzles, accept answers, validate answers, progress teams, handle hints, award points, and manage the game.

The actual Christmas 2026 puzzles should be stored separately as a configurable game package.

For example:

```text
games/
└── christmas-2026/
    ├── game.json
    ├── team-a/
    │   ├── puzzles/
    │   └── assets/
    └── team-b/
        ├── puzzles/
        └── assets/
```

The important principle is:

> **`games/christmas-2026` is data, not application code.**

This means that next year's game should ideally be possible by creating something such as:

```text
games/
├── christmas-2026/
└── christmas-2027/
```

without needing to substantially modify the application itself.

Multiple packages may coexist, for example:

```text
games/
├── christmas-2026-family/
├── christmas-2026-friends/
└── christmas-2026-demo/
```

### Game Package Selection and Run Lifecycle

`READY` represents the condition in which no game is currently active. It does not require a persisted active game run.

While the application is `READY`:

* administrators should be able to see the available game packages under `games/`;
* administrators should select which package to start;
* teams should only see a waiting-for-game-master state;
* inspecting the list of available packages must not itself create an immutable snapshot or start a run.

Starting a game is the boundary at which source configuration becomes live game configuration. When an administrator starts a selected package, the application should:

1. validate the current source package;
2. snapshot the package configuration and every referenced media asset;
3. create a new active run pinned to that immutable snapshot;
4. initialize both teams and their puzzle progress from that snapshot;
5. enter `ADVENT_QUIZ`.

After Start, the active run must use its pinned snapshot. Editing or deleting source files under `games/` must not silently change an active game.

Application, Docker, host, browser, or network restarts are **recovery events, not game resets**. If an active run exists after restart, the application should continue that exact run using persisted state and its pinned snapshot, including progression, points, timers, effects and other durable state.

An administrator's full Reset intentionally ends the active run. Reset should preserve the completed run, its immutable snapshot, receipts and audit history, but should leave **no active replacement run**. The application then returns to `READY`, where an administrator may select the same package or a different package. Starting again creates a new run and a new snapshot from the package's current source files.

The exact puzzle format should therefore be designed to make puzzles easy to create, edit, import, export, and replace.

A puzzle definition should ideally be able to specify things such as:

* Puzzle number
* Puzzle type
* Question/content
* Images
* Audio
* Other media
* Expected answer
* Answer type
* Hint
* Point rewards or costs
* Team-specific content
* Team-specific answer
* Information/fragments awarded upon completion
* Whether previous puzzle information is required
* Any special behaviour

The goal is to make creating the actual Christmas puzzles one of the easiest parts of configuring the application.

## Gaming Element

We would like to interject a gaming element. This is a point-based system. The exact mechanism of how points are earned is currently **a work in progress**.

Points can be used to stall or otherwise interfere with the other team.

The elements are:

### Music Challenge

After a team, doesn't matter which team, finishes puzzle 13, a special **music challenge** will begin.

During this challenge all the main puzzle elements will be paused, and the shop will be unavailable. The game should shift to a new view specifically for this challenge.

All the effects should also be paused, and attacking should be disabled. This is essentially its own mini-game.

This challenge consists of 11 music related questions. Ideally this music should play from the central game overview, that will be displayed on the TV to all players. For each questions, the music will play for as long as no correct answers has been submitted.

The teams can submit the answer (the name of the song) in the view on their device. They can submit as many answers as they wan't, there is no penalty for giving the wrong answer. As soon as the correct answer has been given by a team the next music question will start.

After the last question has been answered the score will be viewed on the central game overview for a minute or three, after which the normal quiz will progress. The views will return to the advent calendar, the shops will be available and the attacks will be enabled again.


### Freezing the other team

The attacking team can spend points to freeze the other team's advent calendar.

The affected team will be unable to interact with the screen for 5 minutes.

The affected team cannot reverse this and must wait out the timer.

Nothing should be available to the "frozen" team, they cannot view questions or hints and cannot submit answers.

### Buying Hints

The team can spend points to purchase a hint for the current puzzle.

There will always be exactly one hint available for a puzzle.

The hint should only be revealed to the team that purchased it.

### Buying Skips

The team can spedn points to purchase a skip for a puzzle.

When the skip is activated the current question will immeadetly be regarded as "solved" and the next advent box will open and that question will start.

### Buying an Uno Reverse

A team can spend points to purchase an Uno Reverse card.

The fact that this card has been purchased is invisible to the other team.

When the Freeze effect is sent to a team with an active Uno Reverse, the attacking team will instead be affected by the adverse effect of the Freeze effect that they intended to send.

### Initiating a Challenge

A team can initiate a challenge. The team that starts the challenge is the *initiatior* while the other team is the *challenged*.

Each team can only initiate this once during the entire game.

**Current approved rule:** starting Challenge costs **0 points**, consumes only that team's one opportunity, and selects a distinct question for that initiating team. A 30-second gathering stage precedes answer availability. The old paid example is superseded.

Both teams will receive the same puzzle which they need to solve.

If the *challenged* team loses (and the *initiator* wins) the *challenged* team will move to the Freeze state.

### Admin Point Assignment

Admins should have the option to assign additional points to teams.

This is because there will be additional physical or written riddles that can be solved during the evening for extra points.

This creates a race where one possible strategy is to finish the puzzles as quickly as possible, while another strategy is to focus on earning points and causing delays for the other team.

## Game Master / Admin Mode

The application should contain a dedicated **Game Master / Admin interface**.

This interface is intended for the two admins who will be responsible for running and supervising the game.

When no game is active, the admin interface should show the available game packages and allow an administrator to select one and start a new run. Starting opens the first advent calendar box for both teams. While a game is active, the interface should provide a comprehensive overview of the current state of the entire game and allow the admins to intervene when necessary.

### Game Overview

The main admin dashboard should display both teams simultaneously.

For each team, the admins should be able to see:

* Current puzzle
* Overall progression, e.g. `13/25`
* Completed puzzles
* Current points
* Active attacks
* Active defensive effects
* Active timers
* Current challenge state
* Hints purchased
* Collected puzzle fragments
* Current game status

A visual representation using two advent calendars is preferred.

The dashboard should update automatically so that admins can monitor the game live.

### Administrative Controls

Admins should be able to manually:

* Reset/end the entire active game and return to game selection
* Award points
* Remove points
* Unlock a puzzle
* Mark a puzzle as solved
* Reset a puzzle
* Skip a puzzle
* Reset team progression where necessary
* Freeze a team
* Remove Freeze from a team
* Pause the entire game
* Resume the entire game
* Trigger an freeze effect
* Remove an freeze effect
* Cancel an active timer
* Add/remove an Uno Reverse
* Provide a hint
* Initiate or resolve a challenge
* Resolve unusual situations manually

These controls are intended primarily as a safety mechanism. The game should normally run automatically according to the defined rules, but the admins should never be forced to modify the database or server directly to resolve a problem during the event.

### Event Log

The application should maintain an event log of important game actions.

Examples:

```text
20:43:12  Team A solved puzzle 8
20:43:28  Team B purchased hint for puzzle 6 (-3 points)
20:44:02  Team A attacked Team B (-8 points)
20:44:02  Team B shield consumed
20:45:17  Admin awarded Team A +5 points
20:47:33  Team B solved puzzle 7
```

The event log should ideally include:

* Timestamp
* Team
* Action
* Result
* Point change
* Source, e.g. team or admin
* Relevant puzzle/effect

This provides both useful live information and a way to reconstruct what happened if there is a dispute or unexpected behaviour.

### Emergency / Game Master Controls

Because this is a live event, the application should assume that unexpected situations can occur.

For example:

* A puzzle contains an unintended ambiguity.
* A physical puzzle component is missing or broken.
* A team accidentally submits an incorrect answer repeatedly.
* A puzzle is accidentally configured incorrectly.
* A team becomes stuck due to a technical issue.
* An attack behaves unexpectedly.
* An admin needs to correct a mistake.

The Game Master interface should therefore allow the admins to override the normal game flow without accessing the server directly.

The goal is that **the admins should be able to resolve virtually any game-state problem from the admin interface itself.**

## Technical Details

This will be hosted on own hardware in a home network.

Devices will use a VPN to tunnel into the network. This gives us some freedom in deploying.

I have personally no previous knowledge about anything front-end related. I did use some Spring Boot a while ago, and databases only on a fairly novice level.

Ideally we keep the implementation as lightweight as possible, but keep a specific emphasis on ease of configuration on the side of the puzzles.

This is the stuff that will probably need to be programmed by hand, and making this easily importable / exportable will also enhance replayability so we could, for example, use the application next year and just swap out the puzzles.

The application should therefore prioritize:

* Simple deployment
* Low resource requirements
* Easy maintenance
* Easy puzzle configuration
* Easy import/export
* Reliable operation on a local network
* Strong separation between team game states
* Simple administration
* Ability to recover from unexpected situations
* Replayability

The application does not need to be designed for public internet deployment. It will run inside the home network and be accessed through the existing VPN infrastructure.

## Data and Game State

The application should distinguish between:

1. **Application logic**
2. **Game configuration**
3. **Persistent game state**
4. **Media/assets**

The application logic contains the generic functionality of the escape room system.

The game configuration contains the specific puzzles, answers, hints, point costs, and other rules for a particular game.

Persistent game state contains information generated while the game is being played, such as team progression, points, timers, and completed puzzles.

Media/assets contain images, audio, and other files required by the puzzles.

When a game starts, the selected source package and referenced media become an immutable run snapshot. The persistent active run points to that snapshot. Source package files remain authoring/input data and are not reread to change an already-active run.

The Christmas 2026 game should therefore be replaceable without modifying the core application.

## Agent Usage

Since the developer will have little to no front-end skills and will be doing the implementation on his own while it needs to be finished before December 10th, we will want to use AI as much as possible.

The selected coding agent should therefore ideally be capable of handling the complete development workflow, including:

* Understanding the overall specification
* Designing the application architecture
* Creating the frontend
* Creating the backend
* Designing the database
* Implementing the game state logic
* Implementing the admin interface
* Implementing the puzzle configuration system
* Creating tests
* Running the application
* Diagnosing errors
* Iterating on the implementation
* Refactoring when necessary
* Assisting with deployment

The developer should not be expected to manually create the frontend architecture or write large amounts of frontend code.

The AI-assisted development process should therefore be treated as an important part of the technical design rather than merely an optional productivity tool.

The implementation should be structured in a way that allows the coding agent to work incrementally, test changes, and maintain a coherent understanding of the application rather than attempting to generate the entire application in one step.

## Initial Development Priorities

The application should ideally be developed in stages:

1. Basic application skeleton
2. Team authentication and strict team isolation
3. Game and puzzle data model
4. Puzzle import/configuration system
5. Basic team current-puzzle interface
6. Answer submission and progression
7. Persistent game state
8. Admin/Game Master interface
9. Point system
10. Attacks and defensive mechanics
11. Timers and challenges
12. Puzzle fragments and final puzzle
13. Event logging
14. Emergency/admin overrides
15. Visual polish
16. Testing
17. Deployment on the home server

The focus should initially be on **correctness and robustness**, with visual polish added after the underlying game mechanics are reliable.
