/* Issue #82: uninterrupted long-question reading on the unattended Challenge TV.
   Only the public, shared question moves; game state remains server-owned. */
(function () {
  "use strict";

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const startHoldMs = 3000;
  const endHoldMs = 4000;
  const pixelsPerSecond = 38;
  let activeKey = null;
  let activatedAt = 0;

  function advance(now) {
    const panel = document.querySelector("[data-tv-challenge-key]");
    if (!panel) {
      activeKey = null;
      return;
    }
    const key = panel.dataset.tvChallengeKey;
    if (key !== activeKey) {
      activeKey = key;
      activatedAt = now;
    }

    const overflow = Math.max(0, panel.scrollHeight - panel.clientHeight);
    if (overflow < 1) return;

    const elapsed = Math.max(0, now - activatedAt);
    let offset;
    if (reducedMotion.matches) {
      // Present each segment without continuous motion, including the end.
      const pageSize = Math.max(1, panel.clientHeight * 0.75);
      const pages = Math.ceil(overflow / pageSize);
      const page = Math.max(0, Math.floor((elapsed - startHoldMs) / 12000));
      offset = Math.min(overflow, (page % (pages + 2)) * pageSize);
    } else {
      const travelMs = overflow * 1000 / pixelsPerSecond;
      const cycleMs = startHoldMs + travelMs + endHoldMs;
      const movingMs = Math.max(0, (elapsed % cycleMs) - startHoldMs);
      offset = Math.min(overflow, movingMs * pixelsPerSecond / 1000);
    }
    panel.scrollTop = offset;
  }

  function frame(now) {
    advance(now);
    window.requestAnimationFrame(frame);
  }

  // HTMX replaces #overview-state every 500ms. Restore the reading position
  // immediately after each swap, without resetting the elapsed reading time.
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.detail.target?.id === "overview-state") {
      advance(performance.now());
    }
  });

  window.requestAnimationFrame(frame);
}());
