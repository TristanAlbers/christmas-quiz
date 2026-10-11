(function () {
  "use strict";

  const observed = new Map();

  function calendarKey(calendar) {
    const state = calendar.closest("[data-run-id]");
    return (state ? state.dataset.runId : "") + ":" + calendar.dataset.teamId;
  }

  function openingEcho(door) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const box = door.getBoundingClientRect();
    const echo = door.cloneNode(true);
    const sourceFlap = door.querySelector(".advent-door__flap");
    const echoFlap = echo.querySelector(".advent-door__flap");
    echo.classList.add("advent-door--opening", "advent-door-opening-echo");
    echo.setAttribute("aria-hidden", "true");
    echo.style.left = box.left + "px";
    echo.style.top = box.top + "px";
    echo.style.width = box.width + "px";
    echo.style.height = box.height + "px";
    echo.style.listStyle = "none";
    if (sourceFlap && echoFlap) {
      echoFlap.style.background = window.getComputedStyle(sourceFlap).background;
    }
    // Keep the echo in the same TV-themed subtree as the real door.
    // A body-level clone falls back to the legacy red reveal for ~1.5s.
    const overlay = door.closest(".public-status--advent") || document.body;
    overlay.appendChild(echo);
    echo.addEventListener("animationend", function (event) {
      // The flap's animation bubbles first; wait for the echo fade to finish.
      if (event.target === echo) echo.remove();
    });
    window.setTimeout(function () { echo.remove(); }, 1800);
  }

  function observeCalendars() {
    document.querySelectorAll(".advent-progress[data-team-id]").forEach(function (calendar) {
      const key = calendarKey(calendar);
      const count = Number(calendar.dataset.completedCount);
      if (!observed.has(key) || count < observed.get(key)) {
        observed.set(key, count);
        return;
      }
      const previous = observed.get(key);
      if (count > previous) {
        for (let number = previous + 1; number <= count; number += 1) {
          const door = calendar.querySelector('[data-door-number="' + number + '"]');
          if (door) openingEcho(door);
        }
        observed.set(key, count);
      }
    });
  }

  // Public TV polls every 500 ms to keep the authoritative clock current.
  // Avoid replacing 50 read-only SVG doors when only that clock changed.
  // Genuine progress, Freeze, Pause, Music, Challenge and run changes still swap.
  document.body.addEventListener("htmx:beforeSwap", function (event) {
    if (!event.detail || event.detail.target?.id !== "overview-state") return;
    const current = event.detail.target.querySelector(".public-status--advent");
    if (!current || !event.detail.xhr || !event.detail.shouldSwap) return;

    const incoming = document.createElement("template");
    incoming.innerHTML = event.detail.xhr.responseText;
    // Preserve HTMX out-of-band updates if the audio context has changed.
    if (incoming.content.querySelector("[hx-swap-oob]")) return;
    const next = incoming.content.querySelector(".public-status--advent");
    if (!next) return;

    const oldClock = current.querySelector(".game-clock strong");
    const newClock = next.querySelector(".game-clock strong");
    if (!oldClock || !newClock) return;
    const nextTime = newClock.textContent;

    // Compare all public Advent markup except the changing HH:MM:SS.
    // This retains the complete live calendar when polling changes nothing.
    const stableCurrent = current.cloneNode(true);
    const stableNext = next.cloneNode(true);
    stableCurrent.querySelector(".game-clock strong").textContent = "";
    stableNext.querySelector(".game-clock strong").textContent = "";
    if (!stableCurrent.isEqualNode(stableNext)) return;

    oldClock.textContent = nextTime;
    event.detail.shouldSwap = false;
  });

  document.addEventListener("DOMContentLoaded", observeCalendars);
  document.body.addEventListener("htmx:afterSettle", function () {
    observeCalendars();
  });
}());
