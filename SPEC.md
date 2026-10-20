# Quizzmas — Midnight Impact animation specification

Date: 20 October 2026  
Status: implementation specification for the selected design direction. The user selected Midnight Impact; final production visuals still require review.  
Scope: team-phone feedback for puzzle completion, UNO Reverse purchase, skipping a puzzle, and buying a hint.

## Purpose and design authority

Give successful player actions the bold, theatrical feedback of the existing animations, rendered in the Midnight Advent visual language. Each event has a recognisable physical object, a deliberate entrance, a readable result, and a clean exit back to the game.

Visual reference: **Midnight Impact** in the second animation exploration shown in this conversation. The approved Midnight Advent reference pack supplies the surrounding phone design, materials, typography, and red Reverse-card language. The exploration is a motion reference, not production markup or authoritative game state. Its sample puzzle, numbers, costs, and explanatory text must not become game rules.

The accepted scope change overrides the exploration: remove every fragment reference from the proposed animations. No fragment icon, count, message, transfer, reward claim, trigger, or animation dependency belongs in this work. Existing fragment mechanics and UI are neither removed nor redesigned by this specification; any phase-out is separate work.

## Confirmed decisions — grilling round 1

- All four actions use a temporary full-phone takeover.
- Puzzle completion shows the numbered door opening. The revealed chocolate must be exactly the same chocolate shown for that door on the game screen: same asset or rendering, shape, motif, material, and door mapping. Scaling for the animation is allowed; a substitute or approximate recreation is not.
- Authoritative interruptions immediately replace local feedback. Interrupted animations are discarded and never replayed afterward. A Reverse-purchase animation yields immediately to an incoming attack and its actual reflection sequence.

## Confirmed decisions — grilling round 2

- Total animation targets: puzzle solved 3.5 seconds; Reverse purchase 3.4 seconds; skip 2.8 seconds; hint purchase 2.7 seconds. Small refinements during production visual review are allowed.
- Players cannot manually dismiss or tap past these animations. Authoritative interruptions still replace them immediately.
- Finishing the final puzzle goes directly to the existing victory sequence, omitting routine completion feedback.

## Confirmed decisions — grilling round 3

- Game clocks, incoming attacks, and authoritative state continue normally during playback. The presentation lock grants no gameplay protection.
- All devices play the normal full animation and duration, including devices requesting reduced motion. Do not substitute a static or shortened confirmation for these four animations. This decision is scoped to these four treatments only; do not change other screens or animations.

The focused grilling questions are settled. The user authorised publication as one GitHub ticket with an asset ZIP on 20 October 2026; production implementation has not started.

## Included and excluded work

Included:

- Replace the existing successful puzzle-completion and Reverse-purchase animations with Midnight Impact treatments.
- Add successful skip and hint-purchase feedback in the same family.
- Integrate authoritative triggers, one-time playback, interruption handling, responsive layout, and consistent full-motion playback.
- Retain the existing underlying game outcomes, prices, availability, and authorisation.

Excluded:

- Fragment work of any kind beyond omitting it from these animations.
- Changes to points, answers, skip eligibility, hint behaviour, inventory rules, or purchase semantics.
- Redesign of attack launch, Freeze impact, actual Reverse reflection, frozen screens, pause, victory, Music Quiz, or Challenge.
- Public TV or Game Master animations, new audio, and the alternative Christmas-theatre direction.

## Shared visual language

Use existing Midnight Advent tokens where available: pine-green and near-black surroundings, warm brass/gold accents, cream text, parchment, and garnet-red card surfaces. Use the existing serif display typography with clear supporting text. Objects should resemble crafted game pieces; avoid emoji or platform-dependent arrow glyphs.

All four treatments use a temporary full-phone takeover, contained within the team screen (confirmed in grilling round 1). It uses a dark material backdrop, a restrained gold frame, soft radial illumination, a large central object, one headline, and one short supporting line. Supporting rays and particles frame the object without overwhelming the text. Reverse purchase may use a deep garnet backdrop.

Motion has four phases: entrance, object action, readable hold, exit. Use one controlled overshoot on entrance, with no repeated bouncing, continuous spinning, rapid flashing, or persistent particle loops. The headline follows the entrance rather than appearing all at once. Text remains readable during the hold.

## Event treatments

The durations below are production targets taken from the selected exploration. They include entrance and exit. Small timing refinements are allowed during visual review without changing the event meaning.

| Event | Object and motion | Dutch copy | Total target |
| --- | --- | --- | --- |
| Puzzle solved | A numbered pine-green Advent door arrives with a short scale-and-rotation impact. A gold ring expands once; a small particle burst disperses. The hinged door opens to reveal the exact same chocolate shown for that door on the game screen. Hold, then recede. | **Goed gevonden!** / **Puzzel opgelost.** | 3.5 s |
| Reverse purchased | The existing red Reverse-card artwork enters large, rotates into view, and settles at a slight angle. One warm gold burst marks successful purchase. Exit, then show the authoritative armed state in the normal resource rack. | **Reverse staat klaar** / **Je volgende Freeze wordt teruggekaatst.** | 3.4 s |
| Puzzle skipped | A parchment page for the skipped puzzle turns away, exposing the next puzzle number. Use a softer entrance and restrained gold accents. It is progression feedback, not a correct-answer celebration. | **Een deur verder** / **Puzzel overgeslagen.** | 2.8 s |
| Hint purchased | A parchment envelope arrives; its flap opens and a hint slip rises into view with a warm light accent. Return to the existing hint presentation. | **Een lichtpuntje** / **Hint gekocht.** | 2.7 s |

### Meaning and content rules

- Use the completed or skipped puzzle number from the confirmed action. Never derive it from a later poll that already refers to another puzzle. Only show a next number when a next Advent puzzle actually exists.
- The chocolate reveal must reuse the exact asset or rendering and the same door-to-chocolate mapping used on the game screen. Match its shape, motif, and material; scale only as needed for the composition. Do not ship the placeholder chocolate from the exploration, substitute a similar chocolate, or create an additional chocolate redesign.
- Buying Reverse arms protection; it does not reflect an attack immediately. No incoming ice, opponent reaction, or reflected attack appears in this purchase treatment. Reuse the stable existing Reverse artwork rather than a Unicode arrow or a new interpretation of the card.
- Hint feedback confirms the purchase. It must preserve the existing distinction between purchasing, making available, and revealing a hint. Do not introduce an extra hint, change consumption, or invent hint content.
- No invented point rewards, costs, balances, or remaining counts appear in animation copy. Existing server-derived information remains authoritative outside the takeover.
- A rejected, unaffordable, duplicate, or unavailable action keeps its existing error/availability feedback and never plays a success animation.

## Triggers and playback lifecycle

1. Start only after the server confirms a new successful action. A button press or speculative local balance change is insufficient.
2. Identify the accepted action through the existing event/action identity where available. Otherwise add the smallest presentation contract necessary to distinguish separate accepted actions. Inspect the repository before choosing the mechanism.
3. Play each accepted event once on its relevant team display. Routine 500 ms polls, dialog updates, retries, and repeated responses must not restart it.
4. Establish a baseline on initial page load or reconnect. Do not replay historical purchases or completions because the current state contains them. New runs must have a distinct baseline.
5. Keep the animation layer independent of poll-replaced content. Underlying game state may update during playback; ending the animation reveals the latest authoritative screen.
6. During playback, block activation of underlying gameplay controls and prevent keyboard focus entering obscured controls. Do not offer a replay or dismiss button in production. This is a presentation lock only; game timers and server state continue normally.
7. Never queue a backlog of stale celebrations. Pause, Freeze/attack, Challenge, Music Quiz, victory, reset, logout, and other authoritative takeovers have priority. Cancel the local feedback and release its presentation lock when one occurs; do not replay it when that state ends.
8. Final completion uses the existing victory flow directly. Do not put this routine door animation ahead of victory or add its duration to the approved victory sequence. A skip that transitions into another game phase similarly yields to that transition.
9. Remove transient elements, timers, input locks, and accessibility state on completion, cancellation, navigation, or run reset. Restore appropriate focus only if its destination still exists in the current authoritative screen.

## Privacy, responsiveness, and accessibility

These animations are private to the acting team. They must not expose its question, hint, inventory, or purchase to the other team, public TV, or unauthorised viewers. Decorative imagery must not embed private answer content.

Fit at 320, 360, 390, and 430 CSS-pixel phone widths, including short-height viewports and safe areas. Scale the object and spacing before shrinking essential text. All copy must fit without clipping, overlapping, or horizontal overflow. Use normal document scrolling when accessibility settings require it.

For these four treatments, play the normal full animation and duration even when the device requests reduced motion (explicit product-owner decision, grilling round 3). Do not provide a static or shortened alternative based on that preference. Scope any styling override narrowly to these treatments; existing reduced-motion behaviour elsewhere remains unchanged. Authoritative interruptions retain priority.

Announce the successful result once through an accessible status region; hide decorative objects and particles from assistive technology. Avoid duplicate announcements from the animation and the existing feedback area.

## Implementation constraints

Use the existing Django templates, HTMX polling, CSS, and small JavaScript lifecycle hooks. No new frontend framework, animation service, worker, or runtime dependency is needed. Read repository AGENTS.md and the current product/UI/polling documents before implementation; their security and game-state contracts remain authoritative.

Keep still-valid input, media, dialog, and control identities stable across polls. Prefer transforms and opacity for motion. Avoid per-frame layout work and animations that reset audio or remount media. Validate the actual card artwork and transforms on Chromium/Android and WebKit/iPhone; visual parity must not rely on native symbol rendering.

## Acceptance and verification

- Each of the four successful actions shows its specified object, message, and final authoritative state.
- Fragment content and dependencies are absent from all four new treatments.
- For a given door, the animation and game screen show the exact same chocolate, with no asset, motif, shape, material, or mapping mismatch.
- Solving and skipping are visually and verbally distinct; skip never claims the answer was correct.
- Purchase feedback is distinct from actual attack/reflection effects, which retain their current behaviour.
- Hint purchase preserves current hint semantics and never leaks or fabricates content.
- Failed requests, repeated responses, and ordinary polls produce no false success or replay.
- Initial load, reconnect, and run reset do not replay old events; later legitimate actions still animate.
- Polling continues through playback without losing answers, resetting media, or breaking controls.
- Background controls cannot submit during the takeover and work normally after completion or interruption.
- Pause, attacks, state transitions, and victory pre-empt routine feedback without stale replay or stuck locks.
- Check all four actions in Chromium and WebKit at representative phone sizes; check narrow/short layouts, increased text size, and both values of the reduced-motion device preference. Verify that both preferences produce the same full sequence and timing for these four treatments.
- Automated coverage should target event identity, rejection, interruption, and cleanup. Visual review should inspect entrance, hold, exit, and final state in the real application, rather than screenshots of this exploration alone.

## Delivery boundary

This document defines the selected direction; it does not claim the repository was inspected or modified. Implementation should be prepared on a separate branch with focused changes and minimal pushes. Present production motion evidence for all four actions before final visual approval. The user authorised creating one implementation issue and publishing this reference package. Production implementation, deployment, merge, and changes to game rules are not part of this handoff task.
