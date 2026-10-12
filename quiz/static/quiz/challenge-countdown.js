/* Display-only countdown. Server polling supplies authoritative remaining time;
   only server transitions reveal the puzzle or enable answers. */
(function () {
  "use strict";

  let sample = null;

  function render() {
    const clock = document.querySelector("[data-challenge-countdown]");
    if (!clock || !sample) return;
    const elapsed = sample.paused ? 0 : performance.now() - sample.receivedAt;
    const seconds = Math.max(0, Math.ceil((sample.remainingMs - elapsed) / 1000));
    const label = sample.paused
      ? `Gepauzeerd met nog ${seconds} seconden`
      : `Begint over ${seconds} seconden`;
    if (clock.textContent !== label) clock.textContent = label;
    clock.dateTime = `PT${seconds}S`;
  }

  function synchronize() {
    const clock = document.querySelector("[data-challenge-countdown]");
    if (!clock) {
      sample = null;
      return;
    }
    // The phone pane is intentionally stable across polls. Read the new
    // authoritative sample from the swapped team-state surface instead.
    const team = document.querySelector(".team-state-surface[data-challenge-countdown-ms]");
    const remainingMs = Number(team ? team.dataset.challengeCountdownMs : clock.dataset.remainingMs);
    if (!Number.isFinite(remainingMs) || remainingMs < 0) return;
    sample = {
      remainingMs,
      paused: team
        ? team.dataset.challengeCountdownPaused === "true"
        : clock.dataset.challengeCountdownPaused === "true",
      receivedAt: performance.now(),
    };
    render();
  }

  document.addEventListener("DOMContentLoaded", synchronize);
  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (["game-status", "overview-state"].includes(event.detail.target?.id)) synchronize();
  });
  document.body.addEventListener("htmx:oobAfterSwap", function (event) {
    if (event.detail.target?.id === "question-pane") synchronize();
  });
  window.setInterval(render, 125);
}());
