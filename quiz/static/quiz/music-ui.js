(function () {
  "use strict";

  function formatCountdown(root) {
    (root || document).querySelectorAll("[data-music-countdown]").forEach((clock) => {
      const output = clock.querySelector("[data-music-countdown-value]");
      const remainingMs = Number(clock.dataset.remainingMs);
      if (!output || !Number.isFinite(remainingMs)) return;

      const seconds = Math.max(0, Math.ceil(remainingMs / 1000));
      const minutes = Math.floor(seconds / 60);
      const remainder = seconds % 60;
      output.textContent = `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
      clock.dateTime = `PT${seconds}S`;
    });
  }

  // Music score winner comes from the server; do not confuse with Advent first-finisher.
  // This overlay is mounted outside HTMX swap targets to survive 500ms polling.
  const finaleOverlay = document.getElementById("music-finale-confetti");
  let lastFinaleKey = null;
  function maybeCelebrateMusic() {
    if (!finaleOverlay) return;
    const marker = document.querySelector("[data-music-finale-winner]");
    if (!marker || !marker.dataset.musicFinaleWinner) return;
    const surface = (document.body.dataset.teamId || "tv").toLowerCase();
    const key = "quizzmas:music-finale:" + marker.dataset.musicFinaleRun + ":" + surface;
    if (lastFinaleKey === key) return;
    try {
      if (window.sessionStorage.getItem(key) === "seen") {
        lastFinaleKey = key;
        return;
      }
      window.sessionStorage.setItem(key, "seen");
    } catch (_error) {
      // In-memory guard still prevents repeats within the page.
    }
    lastFinaleKey = key;
    if (surface !== "tv" && surface !== marker.dataset.musicFinaleWinner) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    finaleOverlay.replaceChildren();
    const colors = ["#ebcb87", "#fff0c2", "#a53746", "#69977d"];
    // Phone celebrations frame the result instead of covering the words.
    const count = surface === "tv" ? 46 : 26;
    for (let i = 0; i < count; i += 1) {
      const piece = document.createElement("i");
      const left = surface === "tv" ? (i * 31) % 99
        : i % 2 === 0 ? (i * 13) % 17 : 83 + (i * 19) % 17;
      piece.style.setProperty("--left", left + "%");
      piece.style.setProperty("--drift", (((i * 23) % 17) - 8) + "vw");
      piece.style.setProperty("--color", colors[i % colors.length]);
      piece.style.setProperty("--delay", ((i % 9) * 0.07) + "s");
      piece.style.setProperty("--duration", (3.2 + (i % 5) * 0.2) + "s");
      finaleOverlay.appendChild(piece);
    }
    window.setTimeout(() => finaleOverlay.replaceChildren(), 4900);
  }
  document.addEventListener("DOMContentLoaded", maybeCelebrateMusic);
  document.body.addEventListener("htmx:afterSettle", maybeCelebrateMusic);
  document.addEventListener("DOMContentLoaded", () => formatCountdown(document));
  document.body.addEventListener("htmx:afterSwap", (event) => {
    formatCountdown(event.detail.target);
  });
  document.body.addEventListener("htmx:oobAfterSwap", (event) => {
    formatCountdown(event.detail.target);
  });
})();
