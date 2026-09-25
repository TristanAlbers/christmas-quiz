# Phase 6 Challenge normal-gameplay contract

Status: Stage A contract amended by explicit user decision, 2026-09-25. Phase 5 is the required baseline.

This contract is subordinate to `docs/product-decisions.md` and the normative game rules. The 2026-09-25 Challenge product decision intentionally overrides older wording that described Challenge as paid, reused one package puzzle, started immediately, or was hidden entirely from the public/TV overview. The Phase 3/5 contracts, Views, architecture, and polling guideline also apply.

## Legality, state, and outcomes

- Each team begins a run with exactly one private Challenge opportunity. Only an authenticated team acting for itself may initiate; no client-supplied team or target identity is trusted. Phase 6 adds no admin initiate/resolve/cancel command—those remain Phase 8 emergency controls.
- Challenge is always free. Starting it never deducts points and affordability is not an eligibility condition. The single-use opportunity is the limiting resource.
- Initiation requires global `ADVENT_QUIZ`, no active Challenge, both teams in effective `PUZZLE` state, neither team finished, and the initiator's opportunity available. Derived UI eligibility never substitutes for this backend recheck.
- One accepted initiation atomically consumes only the initiator's opportunity, selects that initiator's dedicated Challenge puzzle, creates the active Challenge, changes both activity states to `CHALLENGE`, records receipt/audit facts, and commits. Competing initiations serialize; a waiter rereads state and consumes nothing.
- A run can contain at most two normally initiated Challenges: one initiated by Team A and one by Team B. Team A's and Team B's configured Challenge puzzles have different IDs, and persistence prevents a question ID from being reused by two Challenge rows in one run.
- Challenge remains a team-activity mode rather than a new global state. Global state remains `ADVENT_QUIZ`; puzzle progress, fragments, points, inventory, Reverse, and current Advent puzzle remain unchanged. Normal answers, completion, shop, Hint/Skip, attacks, and purchases are illegal for both teams while Challenge is active.
- Initiation begins a 15-second server-authoritative gathering period measured in Advent gameplay time. During it the puzzle, media, and answer control are hidden and answer submissions are rejected. Pause stops this countdown; Resume continues it. Refresh/reconnect/restart recover the same remaining period.
- When the gathering period reaches zero, both teams receive the same selected Challenge puzzle. Attempts are unlimited and penalty-free with no time limit. An accepted wrong attempt changes no live state. The first valid correct-answer transaction accepted by SQLite wins; a waiter rejects the stale Challenge context.
- If the initiator wins, it returns to `PUZZLE` and the challenged team receives a fresh five-minute direct Freeze at the current Advent gameplay time. If the challenged team wins, both return to `PUZZLE` and no Freeze is applied. Neither outcome awards points, completes an Advent puzzle, advances a door, changes fragments, or triggers Music.
- Challenge-loss Freeze uses `apply_direct_freeze`, not the paid player-attack route. It is not redirected by Uno Reverse and does not consume the loser's active Reverse.
- Admin Pause preserves both `CHALLENGE` activity states and the gathering/answer context. Disconnect, refresh, or process restart never resolves or forfeits a Challenge. Full Reset may archive the run normally. Finished teams cannot initiate or participate.

## Transactions, persistence, and package data

Every mutation acquires the established SQLite `IMMEDIATE` writer slot before reading mutable state, reconciles timed/global state, and rechecks actor, run/Challenge/question context and legality. Initiation, accepted attempt, resolution/Freeze, receipt, and append-only audit facts each commit atomically at their applicable command boundary. Client time and network arrival order have no authority.

Migration `0007_phase6_challenge.py` adds durable per-team opportunity state, a run-scoped Challenge record (initiator, challenged team, snapshotted puzzle ID, zero paid cost compatibility fact, start gameplay timestamp, active/resolved status, winner, server timestamps), and append-only attempt/result linkage. Database constraints enforce valid team IDs/result pairing, exactly-zero Challenge cost, one active Challenge per run, one Challenge per initiating team, no question reuse within a run, unique request use, and at most one correct result per Challenge. Phase 6 never deletes these facts.

Same-payload request-ID retries return the committed initiation or answer outcome without another opportunity consumption, attempt, result, Freeze, or audit event. Reuse with different payload is `request_conflict`. Commands carry `run_id`; answers additionally carry active Challenge ID and question ID. Old, fabricated, still-gathering, resolved, paused, reset, or wrong-run contexts are rejected without effects.

Package schema v6 retains `challenge_cost` only as a compatibility/configuration assertion and requires it to be exactly `0`. It contains `challenge_puzzles` with exactly keys `a` and `b`; each value contains ID, title, body, existing answer validator, and a media list, with no reward, hint, or fragment fields. The two Challenge puzzle IDs must be distinct. Initiator A always selects puzzle `a`; initiator B always selects puzzle `b`. Start validates and snapshots all data/media; active runs never reread source files.

Challenge media remains private to authenticated participants/admins in the active context and is unavailable during the gathering period. The public Challenge overview deliberately exposes only the approved text/status projection and never exposes Challenge media.

## Commands, projections, and privacy

The application boundary exposes `initiate_challenge(actor, RunCommand)` and `submit_challenge_answer(actor, SubmitChallengeAnswer)`, with outcomes `challenge_started`, `incorrect`, and `won`. Add `challenge_spent`, `challenge_unavailable`, `challenge_starting`, and `stale_challenge`; retain `stale_question` and `disallowed_state`. `insufficient_points` is not a Challenge rejection because Challenge is free.

Team projection adds private opportunity remaining, `can_initiate`, a nullable coarse reason (`opportunity_spent`, `opponent_unavailable`, or `game_unavailable`), and a nullable Challenge projection. An active projection exposes role plus phase `starting`/`active`, server-derived gathering time remaining, and only exposes the selected question/media after the start period ends. The latest resolved projection contains winner and Freeze-applied result but no answer/attempt history.

Admin projection may show both opportunities, active/resolved status, phase/countdown, initiator, selected puzzle identity, winner, and outcome for monitoring, but adds no Phase 8 controls. It must describe Challenge as free rather than as a purchase.

Public/TV projection gains a deliberately narrow active-Challenge projection. While an active Challenge exists, the overview replaces the normal Advent display with a dedicated Challenge takeover similar in prominence to Music Quiz. It may show Challenge number (1 or 2), initiator/challenged teams, gathering countdown, and after the countdown the shared question title/body. It never includes answer/correct-answer data, attempts, point balances, opportunities remaining, Reverse, Freeze/private effects, or private media. Once Challenge resolves, public display returns to Advent state.

## Presentation, polling, and browser acceptance

Team and admin surfaces target phone/tablet; shared overview targets desktop/TV. The team Sabotage view visually separates Challenge from paid sabotage: Challenge is clearly marked **free / one use per team** and never shows an affordability state. An active Challenge first presents a prominent gather/countdown screen; after zero it changes to the focused shared puzzle/role presentation. Resolution gives persistent, unambiguous win/loss and Freeze/no-Freeze result.

The public/TV Challenge takeover presents a clear two-team race state. During gathering it shows the countdown while withholding the puzzle. After the countdown it shows the shared Challenge prompt and first-correct-wins status. The normal two-calendar overview returns immediately after resolution.

The 500 ms poll may replace read-only status/result/countdown surfaces. Challenge initiation controls remain mounted while run, mode, opportunity, and coarse opponent availability are unchanged. The active answer form is keyed by run + Challenge + question and survives normal polls and incorrect attempts with node identity, focus, value, caret, press, and touch interaction intact. Transition from `starting` to `active`, Pause, resolution, Reset, or genuinely changed eligibility may replace the affected pane.

Focused browser coverage uses representative phone/tablet/TV viewports and proves: free initiation at zero points with balance unchanged; one opportunity per team; two distinct selected puzzles across the two possible Challenges; countdown/puzzle withholding and synchronized reveal; answer rejection during grace; stable active answer interaction; pause-safe gathering; both outcomes; and public takeover/return without private leakage.

## Ownership and gate

Stage ownership remains the repository-standard Phase 6 sequence: domain, persistence/security, integration/projections/data/docs, UI/browser, then independent invariant verification.

The gate requires both outcomes; reversed initiation and correct-answer races; exactly-once opportunity/result/Freeze; zero point delta; two distinct per-initiator puzzles with no question reuse; server-authoritative pause-safe gathering; no reward/progression/Music; Reverse preservation; pause/reconnect/restart and source-deletion recovery; finished-team rejection; strict isolation; public Challenge takeover privacy; polling/browser acceptance; and final GitHub Actions green.
