# Issue #102 — live integration visual checkpoint

Branch: `feat/102-shaped-chocolate-clues` from main
`37bebd2ee9d870bc3ffef4d0e3fe46caf2acb611`. Visual checkpoint pushed at the user’s request for server testing.
The user explicitly approved the live implementation, including the fullscreen
sizing correction, on 2026-10-18. Final verification/review status is below.

- [Approved actual-asset layout reference](issue-102/approved-all-open-reference.png)
- [Real Django overview: A 13/25, B 10/25](issue-102/partial-1920x1080.png)
- [Real Django overview: both 25/25](issue-102/full-1920x1080.png)

All images are 1920×1080. The source concept and enlarged asset sheet were also
inspected in the supplied #101 ZIP. Its hash and all 11 original PNG hashes match
the supplied manifest. No artwork regenerated or modified.

The screenshots use the existing browser test's disposable Django/SQLite fixture
and actual `/overview/` requests, local collected static assets, real projections
and 500 ms HTMX polling. Full progress is seeded without first-winner history so
the existing final victory overlay does not cover the artwork. It is an artwork
inspection fixture, not a change to completion rules or the production finale.

## Smoke evidence

- All 25 slots per team checked against the manifest; repeated subjects resolve
  to identical local asset URLs. Both teams agree.
- Partial state renders only the 23 earned chocolates; full state renders 50.
  Completed numbers are absent; closed numbers remain.
- Every artwork viewport fits inside its door opening, using proportional
  `xMidYMid meet` geometry and the handoff's padded visible bounds. Wings,
  antlers, figures and the lights cable are visually intact.
- All asset requests/decode checks succeeded; no page errors or HTTP failures.
- Calendar DOM identity survives unchanged polls; no initial reveal echo.
- Existing public Freeze/privacy and reduced-motion admin-completion browser
  smoke passed. All three existing calendar presentation checks passed, with
  the earned-only assertion updated for the new contract.
- Django system checks and `git diff --check` passed.

Only render and immediately implicated smoke checks run. Final browser matrix,
canonical completion/recovery checks, CI, Ponytail and Codex review remain after
explicit user approval. Existing browser assertions about the old decorative
cycle must then be adapted to the approved fixed/earned-only artwork contract.

## Differences from the handoff preview

1. Existing production header, clock, audio controls and cabinet layout consume
   more vertical space, so chocolates are smaller than the simplified full-open
   reference. These unrelated elements remain unchanged as requested.
2. Existing production hinges and open flap edges remain; the preview illustrates
   simpler gold door edges. Original PNGs, proportions and mapping match.

Live visual approval is pending. #102 and parent #100 remain open; no merging.


## Fullscreen sizing correction — visual approval pending

The initial server checkpoint (`de9e7c5`) let the igloo/train grow from about
77 px wide at 1920×900 to 116 px at 1920×1080. Clearance from the retained
open-door edge shrank from 22 px to about 2 px, allowing its shadow to overlap
the artwork. Checking containment in the whole opening alone missed this.

The correction reserves equal horizontal space on both sides, based on the
existing open-door edge width plus 12 px. Artwork remains centred on the whole
opening: it is not shifted right to avoid the hinge. Igloo/train also use a
76%-height optical box rather than the default 84%, reducing their visual weight
when the available height controls their size. Original PNGs/viewports and all
hinges, door layout, state and animation/polling code remain unchanged.

Updated live comparisons (both calendars fully revealed):
- [Windowed-height viewport, 1920×900](issue-102/full-1920x900.png)
- [Fullscreen-height viewport, 1920×1080](issue-102/full-1920x1080.png)
- [Larger fullscreen viewport, 2560×1440](issue-102/full-2560x1440.png)

The partial/full 1920×1080 screenshots above have also been refreshed. Disposable
Django render smoke covered both progress states at all three sizes: exact
25-door mappings for both teams, earned-only images, original local asset loads,
no clipped artwork, equal horizontal/vertical scale and no historical reveal
echo. Unchanged polling preserved calendar identity at 1920×1080.

Measured visible artwork bounds remain centred on each opening within 0.01 px
in both axes. Minimum clearance from the open-door edge across all 50 chocolates
is 13 px at both 1920px-wide sizes and at least 13.5 px at 2560×1440. Igloo/train
clearance is 25.5 px at 1920×900, 13 px at 1920×1080 and 13.6 px at 2560×1440.
The three existing calendar presentation checks also passed. Final verification
and reviews still await explicit user visual confirmation.


## Approved live implementation — final verification

On 2026-10-18 the user approved the corrected live implementation and authorized
completion. Earlier pending-approval notes above describe historical checkpoints.

Focused Chromium verification passed: 9 tests covering all 25 mapped doors,
11 original PNG hashes, repeated asset identity, both teams, earned-only
rendering, canonical answer/Skip/admin completion, a real reset/new run,
one-shot animation across polls, refresh recovery, public Freeze/privacy,
reduced motion and artwork geometry at 1024×768, 1280×720, 1920×900,
1920×1080 and 2560×1440. Changed Python passes Ruff. All three focused calendar browser tests also passed locally in WebKit,
including reveal/reload, reduced motion/privacy and all five overview sizes.
The existing WebKit CI job now includes those calendar tests.

The draft CI failures at the prior visual checkpoint were diagnosed: changed
integration-test import ordering and obsolete 25-decorative-motif assertions
are corrected; an unrelated frozen-phone font-measurement failure passed
focused reproduction without changing that screen or test.

Required CI and exact-pair Ponytail/Codex review evidence are recorded on PR #104.
The PR remains draft until the required gates pass; no merge is authorized.
