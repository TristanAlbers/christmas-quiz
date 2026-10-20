# Quizzmas — Midnight Impact reference handoff

Approved direction and single-ticket handoff, 20 October 2026.

## Use

Extract the ZIP and open `midnight-impact-demo.html` in a browser. It runs offline with local assets. Press one of the four labelled buttons to play a complete example. Buttons stay disabled during playback. There is no replay/dismiss control inside the depicted phone.

`SPEC.md` is the written acceptance contract. The demo illustrates composition and motion, not production state, backend triggers, interruptions, or security. Dutch copy and all four durations reflect the concluded grill-with-docs session. There are no fragment visuals or animation dependencies in the demo.

## Assets

- `assets/`: the 11 exact, unmodified transparent chocolate PNGs already used by the game, plus the existing original Reverse arrow geometry extracted as a standalone SVG. Do not reimport duplicates into production; reuse the current app components and source assets.
- `chocolate_manifest.json`: the source manifest, including the exact fixed door mapping and asset hashes. Its historical handoff-status string is preserved verbatim; the PNGs and mapping are now present in the current application.
- `ASSET-PROVENANCE.json`: repository commit and source locations.
- `LICENSE.md`: the repository licence as present at the source commit. This reference package does not grant different rights.

The sample is door 14, which maps to **sneeuwpop**. The demo uses that exact image and the same visible-bounds viewport calculation as the application. Production must use the authoritative completed door and the shared mapping for every door, never the hardcoded demo number.

The red card in the demo establishes the motion and materials. Production must reuse its existing approved card component/arrow artwork, including the established iPhone rendering fix. The hint envelope confirms a purchase; the sample token count is illustrative, and consuming a token to reveal a hint remains a separate action.

## Confirmed decisions

All four actions take over the phone and cannot be manually dismissed. Targets: solved 3.5 s, Reverse purchase 3.4 s, skip 2.8 s, hint purchase 2.7 s. Game clocks and attacks continue. Authoritative takeovers interrupt and discard local feedback. Final completion goes straight to the existing victory sequence. The four full animations also play when reduced motion is requested; this is a narrowly scoped later product decision, not a change to other screens.

The implementation must record that narrow motion exception in the authoritative product/UI documentation as part of the same ticket. Preserve all other accessibility, privacy, recovery, and server-authority requirements.

## Verification boundary

See `REFERENCE-CHECKS.md` for checks actually performed. The reference is not evidence of real Django/HTMX acceptance or device parity. Implementation still requires the existing visual-first checkpoint against the real application, user visual approval, focused tests, CI, and required reviews.

This is an asset-only reference branch/package. Do not merge its branch into the application. Implement the issue on a fresh branch from current main.
