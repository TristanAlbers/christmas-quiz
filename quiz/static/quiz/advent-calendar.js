(function () {
  "use strict";

  const observed = new Map();

  function calendarKey(calendar) {
    const state = calendar.closest("[data-run-id]");
    return (state ? state.dataset.runId : "") + ":" + calendar.dataset.teamId;
  }

  function openingEcho(door) {
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
    document.body.appendChild(echo);
    echo.addEventListener("animationend", function () { echo.remove(); }, { once: true });
    window.setTimeout(function () { echo.remove(); }, 1800);
  }

  function observeCalendars() {
    document.querySelectorAll("#overview-state .advent-progress[data-team-id]").forEach(function (calendar) {
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

  document.addEventListener("DOMContentLoaded", observeCalendars);
  document.body.addEventListener("htmx:afterSettle", function (event) {
    if (event.detail.target && event.detail.target.id === "overview-state") observeCalendars();
  });
}());
