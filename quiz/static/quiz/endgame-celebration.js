(function () {
  "use strict";

  const overlay = document.getElementById("endgame-celebration");
  if (!overlay) return;

  const confetti = overlay.querySelector(".endgame-celebration__confetti");
  const icon = overlay.querySelector("[data-endgame-icon]");
  const eyebrow = overlay.querySelector("[data-endgame-eyebrow]");
  const title = overlay.querySelector("[data-endgame-title]");
  const copy = overlay.querySelector("[data-endgame-copy]");
  const surface = document.body.dataset.endgameSurface || "unknown";
  const currentTeam = (document.body.dataset.teamId || "").toLowerCase();
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let hideTimer = null;

  function marker() {
    return document.querySelector("[data-endgame-state]");
  }

  function storageKey(stateMarker) {
    const runId = stateMarker.dataset.endgameRunId || stateMarker.dataset.runId || "active";
    const scope = surface === "team" ? currentTeam + ":" + runId : "shared:" + runId;
    return "christmas-quiz:endgame-seen:" + surface + ":" + scope;
  }

  function storedValue(key) {
    try {
      return window.sessionStorage.getItem(key);
    } catch (_error) {
      return overlay.dataset.lastWinner || null;
    }
  }

  function remember(key, winner) {
    overlay.dataset.lastWinner = winner;
    try {
      window.sessionStorage.setItem(key, winner);
    } catch (_error) {
      // The in-memory marker still prevents 500 ms polling from replaying it.
    }
  }

  function forget(key) {
    overlay.dataset.lastWinner = "";
    try {
      window.sessionStorage.removeItem(key);
    } catch (_error) {
      // No persistent browser storage is required for correctness.
    }
  }

  function resultCopy(winner) {
    const teamName = winner.toUpperCase();
    if (surface === "overview") {
      return {
        kind: "overview-winner",
        icon: "✦",
        eyebrow: "De eerste 25 deuren zijn geopend",
        title: "Team " + teamName + " wint!",
        copy: "Het andere team speelt verder",
      };
    }
    if (currentTeam === winner) {
      return {
        kind: "winner",
        icon: "✦",
        eyebrow: "Jullie waren als eerste klaar",
        title: "Jullie winnen!",
        copy: "Jullie hebben als eerste alle 25 adventvakjes voltooid. Het andere team speelt verder.",
      };
    }
    return {
      kind: "runner-up",
      icon: "🦌",
      eyebrow: "De race heeft een winnaar",
      title: "Team " + teamName + " was eerder",
      copy: "Rudolph kijkt wat beteuterd, maar jullie huidige puzzel is nog actief. Ga door!",
    };
  }

  function addConfetti() {
    if (reducedMotion || !confetti) return;
    confetti.replaceChildren();
    for (let index = 0; index < 42; index += 1) {
      const piece = document.createElement("i");
      piece.className = "endgame-confetti__piece";
      piece.style.setProperty("--confetti-left", ((index * 37) % 101) + "%");
      piece.style.setProperty("--confetti-drift", (((index * 29) % 17) - 8) + "vw");
      piece.style.setProperty("--confetti-rotate", ((index * 53) % 180) + "deg");
      piece.style.setProperty("--confetti-delay", ((index % 9) * -0.16) + "s");
      piece.style.setProperty("--confetti-duration", (2.7 + (index % 7) * 0.18) + "s");
      confetti.appendChild(piece);
    }
  }

  function hideCelebration() {
    overlay.classList.remove("endgame-celebration--visible");
    overlay.setAttribute("aria-hidden", "true");
    if (confetti) confetti.replaceChildren();
  }

  function showCelebration(winner) {
    const result = resultCopy(winner);
    window.clearTimeout(hideTimer);
    overlay.classList.remove(
      "endgame-celebration--winner",
      "endgame-celebration--overview-winner",
      "endgame-celebration--runner-up"
    );
    overlay.classList.add("endgame-celebration--" + result.kind);
    overlay.dataset.endgameResult = result.kind;
    icon.textContent = result.icon;
    eyebrow.textContent = result.eyebrow;
    title.textContent = result.title;
    copy.textContent = result.copy;
    if (result.kind !== "runner-up") addConfetti();
    overlay.setAttribute("aria-hidden", "false");
    window.requestAnimationFrame(function () {
      overlay.classList.add("endgame-celebration--visible");
    });
    hideTimer = window.setTimeout(
      hideCelebration,
      result.kind === "runner-up" ? 3200 : 4800
    );
  }

  function observeEndgame(initial = false) {
    const stateMarker = marker();
    if (!stateMarker) return;
    const winner = (stateMarker.dataset.endgameWinner || "").trim().toLowerCase();
    const key = storageKey(stateMarker);
    if (!winner) {
      forget(key);
      return;
    }
    if (storedValue(key) === winner) return;
    // A fresh/reconnected page renders the durable server result but must not
    // replay the transient celebration for a finish it did not observe.
    if (initial) {
      remember(key, winner);
      return;
    }
    remember(key, winner);
    showCelebration(winner);
  }

  document.addEventListener("DOMContentLoaded", function () { observeEndgame(true); });
  document.body.addEventListener("htmx:afterSettle", function () { observeEndgame(false); });
}());
