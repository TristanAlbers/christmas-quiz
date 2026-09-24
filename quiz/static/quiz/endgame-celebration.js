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
    const runId = stateMarker.dataset.endgameRunId || "active";
    const scope = surface === "team" ? currentTeam + ":" + runId : "shared";
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
        icon: "🎉",
        eyebrow: "Advent race winner",
        title: "Team " + teamName + " wins!",
        copy: "First to complete all 25 Advent doors. The other team keeps playing.",
      };
    }
    if (currentTeam === winner) {
      return {
        kind: "winner",
        icon: "🏆",
        eyebrow: "You finished first",
        title: "You won the Advent race!",
        copy: "Merry Christmas, champions. The other team can still complete its calendar.",
      };
    }
    return {
      kind: "runner-up",
      icon: "🦌",
      eyebrow: "The race has a winner",
      title: "Team " + teamName + " got there first",
      copy: "Rudolph looks a little glum, but your current puzzle is still active. Keep going!",
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

  function observeEndgame() {
    const stateMarker = marker();
    if (!stateMarker) return;
    const winner = (stateMarker.dataset.endgameWinner || "").trim().toLowerCase();
    const key = storageKey(stateMarker);
    if (!winner) {
      forget(key);
      return;
    }
    if (storedValue(key) === winner) return;
    remember(key, winner);
    showCelebration(winner);
  }

  document.addEventListener("DOMContentLoaded", observeEndgame);
  document.body.addEventListener("htmx:afterSettle", observeEndgame);
}());
