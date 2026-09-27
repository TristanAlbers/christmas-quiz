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

  document.addEventListener("DOMContentLoaded", () => formatCountdown(document));
  document.body.addEventListener("htmx:afterSwap", (event) => {
    formatCountdown(event.detail.target);
  });
  document.body.addEventListener("htmx:oobAfterSwap", (event) => {
    formatCountdown(event.detail.target);
  });
})();
