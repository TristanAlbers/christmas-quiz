(function () {
  "use strict";

  // Projected Music time remains server-authoritative. A small local
  // display ticker fills gaps between 500ms polling snapshots; it never
  // advances a question or decides when Advent restarts.
  const countdownSnapshots = new WeakMap();
  const progressSnapshots = new WeakMap();
  const DECORATIVE_DURATION_MS = 180000;

  function syncMusicVisuals() {
    document.querySelectorAll("[data-music-countdown]").forEach((clock) => {
      // The final phone card deliberately survives ordinary HTMX polls.
      // Its new authoritative remaining time is in the freshly swapped status.
      const source = clock.closest(".music-quiz--phone--final")
        ? document.querySelector("[data-music-final-sync]")
        : clock;
      if (!source) return;
      const remainingMs = Number(source.dataset.remainingMs);
      if (!Number.isFinite(remainingMs) || remainingMs < 0) return;
      countdownSnapshots.set(clock, {
        remainingMs,
        running: source.dataset.running === "true",
        observedAt: performance.now(),
      });
    });
    document.querySelectorAll("[data-music-player-progress]").forEach((bar) => {
      const elapsedMs = Number(bar.dataset.questionElapsedMs);
      if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return;
      progressSnapshots.set(bar, {
        elapsedMs,
        running: bar.dataset.running === "true",
        observedAt: performance.now(),
      });
    });
    tickMusicVisuals();
  }

  function tickMusicVisuals() {
    const now = performance.now();
    document.querySelectorAll("[data-music-countdown]").forEach((clock) => {
      const snapshot = countdownSnapshots.get(clock);
      const output = clock.querySelector("[data-music-countdown-value]");
      if (!snapshot || !output) return;
      const remainingMs = Math.max(0, snapshot.remainingMs -
        (snapshot.running ? now - snapshot.observedAt : 0));
      const seconds = Math.ceil(remainingMs / 1000);
      const minutes = Math.floor(seconds / 60);
      const remainder = seconds % 60;
      output.textContent = `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
      clock.dateTime = `PT${seconds}S`;
    });
    document.querySelectorAll("[data-music-player-progress]").forEach((bar) => {
      const snapshot = progressSnapshots.get(bar);
      if (!snapshot) return;
      const elapsedMs = snapshot.elapsedMs +
        (snapshot.running ? now - snapshot.observedAt : 0);
      const fraction = Math.max(0, Math.min(1, elapsedMs / DECORATIVE_DURATION_MS));
      bar.style.setProperty("--music-progress", (fraction * 100) + "%");
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
  document.addEventListener("DOMContentLoaded", syncMusicVisuals);
  document.body.addEventListener("htmx:afterSwap", syncMusicVisuals);
  document.body.addEventListener("htmx:oobAfterSwap", syncMusicVisuals);
  window.setInterval(tickMusicVisuals, 100);
})();
