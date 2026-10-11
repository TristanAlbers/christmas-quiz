(function () {
  "use strict";

  const observed = new Map();

  // Approved V4 engraved Christmas motifs, repeated deterministically every 11 doors.
  // The number comes from the public calendar; these SVGs encode no game state.
  const motifs = [
    [
      "kerstbal",
      "<circle cx=\"16\" cy=\"18\" r=\"9\"/><path d=\"M13 8V5h6v3M16 5V2M16 2h3M11 16c2-2 4-2 6 0\"/>"
    ],
    [
      "maretak",
      "<path d=\"M16 16V5M16 16c-4-9-11-11-12-5 4 5 9 6 12 5ZM16 16c4-9 11-11 12-5-4 5-9 6-12 5Z\"/><circle cx=\"12\" cy=\"21\" r=\"2\"/><circle cx=\"19\" cy=\"23\" r=\"2\"/><circle cx=\"16\" cy=\"27\" r=\"2\"/>"
    ],
    [
      "kerstbel",
      "<path d=\"M10 22V14c0-5 3-8 6-8s6 3 6 8v8l3 3H7l3-3ZM13 26c0 5 6 5 6 0M16 6V3\"/>"
    ],
    [
      "Rudolph",
      "<path d=\"M11 19 6 8 2 5M11 14 4 13M21 19l5-11 4-3M21 14l7-1M10 18c-3 11 15 12 13 0-2-8-11-8-13 0Z\"/><circle cx=\"12\" cy=\"19\" r=\".8\"/><circle cx=\"20\" cy=\"19\" r=\".8\"/><circle cx=\"16\" cy=\"24\" r=\"2.2\"/>"
    ],
    [
      "peperkoekmannetje",
      "<circle cx=\"16\" cy=\"7\" r=\"4\"/><path d=\"m12 12-5 1-4 6 3 3 6-3v4l-3 6 4 2 3-6 3 6 4-2-3-6v-4l6 3 3-3-4-6-5-1\"/><circle cx=\"16\" cy=\"16\" r=\"1\"/><circle cx=\"16\" cy=\"20\" r=\"1\"/>"
    ],
    [
      "kerstsok",
      "<path d=\"M13 4h10v6h-2v8c0 7-6 10-13 7l-3-3c-2-4 1-8 5-7l3 1V10h-2V4h2ZM13 10h8M7 21l6 3\"/>"
    ],
    [
      "schaats",
      "<path d=\"M6 6h12l3 10 5 5H6V6ZM5 25h22M6 28h20M9 21v4m13-4v4M9 10h6\"/>"
    ],
    [
      "kerstboom",
      "<path d=\"M16 3 8 13h4L6 21h6l-3 5h14l-3-5h6l-6-8h4L16 3ZM16 26v4\"/><circle cx=\"16\" cy=\"11\" r=\"1\"/><circle cx=\"12\" cy=\"20\" r=\"1\"/><circle cx=\"20\" cy=\"20\" r=\"1\"/>"
    ],
    [
      "zuurstok",
      "<path d=\"M10 27V11a7 7 0 0 1 14 0c0 4-6 5-7 1M10 22h6M10 14l7 4M14 5l7 8\"/>"
    ],
    [
      "sneeuwpop",
      "<circle cx=\"16\" cy=\"10\" r=\"5\"/><circle cx=\"16\" cy=\"22\" r=\"8\"/><path d=\"M6 6h20M11 5h10V2H11V5ZM8 19l-5-2m21 2 5-2\"/><circle cx=\"16\" cy=\"20\" r=\".7\"/><circle cx=\"16\" cy=\"24\" r=\".7\"/>"
    ],
    [
      "cadeau",
      "<rect x=\"5\" y=\"12\" width=\"22\" height=\"16\" rx=\"1\"/><path d=\"M3 9h26v5H3zM16 9v19M16 9c-12 0-13-8-7-8 5 0 7 8 7 8ZM16 9c12 0 13-8 7-8-5 0-7 8-7 8Z\"/>"
    ]
  ];

  function embossChocolates() {
    document.querySelectorAll(".advent-door[data-door-number]").forEach(function (door) {
      const chocolate = door.querySelector(".advent-door__chocolate");
      if (!chocolate || chocolate.querySelector("svg")) return;
      const number = Number(door.dataset.doorNumber);
      if (!Number.isInteger(number) || number < 1 || number > 25) return;
      const motif = motifs[(number - 1) % motifs.length];
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("viewBox", "0 0 32 32");
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("class", "advent-door__motif");
      svg.innerHTML = motif[1];
      chocolate.appendChild(svg);
      chocolate.dataset.motif = motif[0];
    });
  }


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
    document.body.appendChild(echo);
    echo.addEventListener("animationend", function () { echo.remove(); }, { once: true });
    window.setTimeout(function () { echo.remove(); }, 1800);
  }

  function observeCalendars() {
    embossChocolates();
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

  document.addEventListener("DOMContentLoaded", observeCalendars);
  document.body.addEventListener("htmx:afterSettle", function () {
    observeCalendars();
  });
}());
