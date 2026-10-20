(function () {
  "use strict";

  const feedback = {
    puzzle_solved: {
      className: "solved",
      duration: 3500,
      title: "Goed gevonden!",
      copy: "Puzzel opgelost.",
    },
    reverse_purchased: {
      className: "reverse",
      duration: 3400,
      title: "Reverse staat klaar",
      copy: "Je volgende Freeze wordt teruggekaatst.",
    },
    puzzle_skipped: {
      className: "skipped",
      duration: 2800,
      title: "Een deur verder",
      copy: "Puzzel overgeslagen.",
    },
    hint_purchased: {
      className: "hint",
      duration: 2700,
      title: "Een lichtpuntje",
      copy: "Hint gekocht.",
    },
  };

  const seenEventIds = new Set();
  const actionEpochs = new Map();
  let active = null;
  let cleanupTimer = null;
  let interruptionEpoch = 0;
  let lastGameplayInterruptionId = null;
  let maxGameplayElapsedMs = 0;

  function overlay() {
    return document.getElementById("routine-feedback");
  }

  function stateSurface() {
    return document.querySelector("#game-status [data-routine-run-id]");
  }

  function normalized(value) {
    return value === null || value === undefined ? "" : String(value);
  }

  function currentContext() {
    const surface = stateSurface();
    if (!surface) return null;
    return {
      runId: surface.dataset.routineRunId || "",
      globalState: surface.dataset.routineGlobalState || "",
      teamState: surface.dataset.routineTeamState || "",
      questionId: surface.dataset.routineQuestionId || "",
      musicPhase: surface.dataset.routineMusicPhase || "",
      challengePhase: surface.dataset.routineChallengePhase || "",
      firstFinisherTeamId: surface.dataset.routineFirstFinisher || "",
      gameplayElapsedMs: Number(surface.dataset.routineGameplayElapsed || 0),
    };
  }

  function contextHasTakeover(context) {
    return !context
      || context.globalState !== "ADVENT_QUIZ"
      || context.teamState !== "PUZZLE"
      || Boolean(context.musicPhase)
      || Boolean(context.challengePhase);
  }

  function isCurrent(detail) {
    const current = currentContext();
    if (!current || !detail || detail.version !== 1 || !detail.state) return false;
    if (detail.runId !== current.runId) return false;
    return [
      "globalState",
      "teamState",
      "questionId",
      "musicPhase",
      "challengePhase",
      "firstFinisherTeamId",
    ].every((key) => normalized(detail.state[key]) === current[key]);
  }

  function hasHigherPrioritySurface() {
    const current = currentContext();
    if (!current) return true;
    return contextHasTakeover(current)
      || document.body.classList.contains("gameplay-film-active");
  }

  function makeSvg(viewBox) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", viewBox);
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    return svg;
  }

  function reverseObject() {
    const card = document.createElement("div");
    card.className = "routine-feedback__reverse-card";
    const oval = document.createElement("span");
    const svg = makeSvg("0 0 70 84");
    for (const pathData of [
      "M20 28 C20 13 47 9 49 26 L54 26 44 40 34 26 39 26 C37 20 27 23 27 30",
      "M50 56 C49 71 22 74 20 57 L15 57 25 44 35 57 30 57 C32 64 43 61 43 54",
    ]) {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", pathData);
      path.setAttribute("fill", "none");
      svg.appendChild(path);
    }
    oval.appendChild(svg);
    card.appendChild(oval);
    return card;
  }

  function doorObject(puzzle) {
    if (!puzzle?.chocolate) return null;
    const door = document.createElement("div");
    door.className = "routine-feedback__door";
    door.dataset.doorNumber = String(puzzle.number);
    const chocolate = document.createElement("div");
    chocolate.className = "routine-feedback__chocolate";
    if (puzzle.chocolate.isBroad) {
      chocolate.classList.add("routine-feedback__chocolate--broad");
    }
    chocolate.dataset.chocolateSubject = puzzle.chocolate.subject;
    const svg = makeSvg(puzzle.chocolate.viewBox);
    const image = document.createElementNS("http://www.w3.org/2000/svg", "image");
    image.setAttribute("href", puzzle.chocolate.staticUrl);
    image.setAttribute("width", String(puzzle.chocolate.width));
    image.setAttribute("height", String(puzzle.chocolate.height));
    svg.appendChild(image);
    chocolate.appendChild(svg);
    const front = document.createElement("div");
    front.className = "routine-feedback__door-front";
    front.textContent = String(puzzle.number);
    door.append(chocolate, front);
    return door;
  }

  function skipObject(puzzle) {
    if (!puzzle) return null;
    const pages = document.createElement("div");
    pages.className = "routine-feedback__pages";
    if (puzzle.nextNumber !== undefined && puzzle.nextNumber !== null) {
      const next = document.createElement("div");
      next.className = "routine-feedback__page routine-feedback__page--next";
      const nextLabel = document.createElement("small");
      nextLabel.textContent = "VOLGENDE PUZZEL";
      const nextNumber = document.createElement("strong");
      nextNumber.textContent = String(puzzle.nextNumber);
      next.append(nextLabel, nextNumber);
      pages.appendChild(next);
    }
    const current = document.createElement("div");
    current.className = "routine-feedback__page routine-feedback__page--current";
    const currentLabel = document.createElement("small");
    currentLabel.textContent = "OVERSLAAN";
    const currentNumber = document.createElement("strong");
    currentNumber.textContent = String(puzzle.number);
    current.append(currentLabel, currentNumber);
    pages.appendChild(current);
    return pages;
  }

  function hintObject() {
    const envelope = document.createElement("div");
    envelope.className = "routine-feedback__envelope";
    const flap = document.createElement("div");
    flap.className = "routine-feedback__flap";
    const letter = document.createElement("div");
    letter.className = "routine-feedback__letter";
    letter.textContent = "?";
    envelope.append(flap, letter);
    return envelope;
  }

  function objectFor(detail) {
    if (detail.kind === "puzzle_solved") return doorObject(detail.puzzle);
    if (detail.kind === "puzzle_skipped") return skipObject(detail.puzzle);
    if (detail.kind === "reverse_purchased") return reverseObject();
    if (detail.kind === "hint_purchased") return hintObject();
    return null;
  }

  function fillParticles(root) {
    root.replaceChildren();
    for (let index = 0; index < 26; index += 1) {
      const particle = document.createElement("span");
      const angle = index * Math.PI * 2 / 26;
      const radius = 90 + (index % 4) * 23;
      particle.className = "routine-feedback__particle";
      particle.style.setProperty("--particle-x", `${Math.cos(angle) * radius}px`);
      particle.style.setProperty("--particle-y", `${Math.sin(angle) * radius}px`);
      particle.style.setProperty("--particle-width", `${index % 3 + 2}px`);
      particle.style.setProperty("--particle-height", `${index % 4 + 3}px`);
      root.appendChild(particle);
    }
  }

  function releaseLock() {
    document.body.classList.remove("routine-feedback-active");
    window.syncTeamPresentationLock?.();
  }

  function cancel(reason) {
    window.clearTimeout(cleanupTimer);
    cleanupTimer = null;
    const film = overlay();
    if (film) {
      film.hidden = true;
      film.className = "routine-feedback";
      film.removeAttribute("data-event-id");
      film.removeAttribute("data-kind");
    }
    const restore = active?.restoreFocus;
    const selection = active?.selection;
    active = null;
    releaseLock();
    if (reason === "complete" && restore?.isConnected && !hasHigherPrioritySurface()) {
      restore.focus({preventScroll: true});
      if (selection && selection.every(Number.isInteger)) {
        restore.setSelectionRange(selection[0], selection[1]);
      }
    }
  }

  window.cancelRoutineFeedback = cancel;

  function start(detail) {
    const config = feedback[detail.kind];
    const film = overlay();
    const object = objectFor(detail);
    if (!config || !film || !object) return;

    cancel("replaced");
    const focused = document.activeElement;
    const restoreFocus = focused?.matches("input, textarea, select, button")
      ? focused : null;
    const selection = restoreFocus?.matches("input, textarea")
      ? [restoreFocus.selectionStart, restoreFocus.selectionEnd] : null;
    const shop = document.getElementById("team-shop-dialog");
    if (shop?.open) shop.close();

    film.className = `routine-feedback routine-feedback--${config.className}`;
    film.dataset.eventId = detail.eventId;
    film.dataset.kind = detail.kind;
    film.style.setProperty("--routine-duration", `${config.duration}ms`);
    film.querySelector(".routine-feedback__object").replaceChildren(object);
    film.querySelector("h2").textContent = config.title;
    film.querySelector(".routine-feedback__copy p").textContent = config.copy;
    fillParticles(film.querySelector(".routine-feedback__particles"));
    film.hidden = false;
    document.body.classList.add("routine-feedback-active");
    window.syncTeamPresentationLock?.();
    const announcement = document.getElementById("routine-feedback-announcement");
    if (announcement) announcement.textContent = `${config.title}. ${config.copy}`;
    const ordinaryFeedback = document.getElementById("action-feedback");
    if (ordinaryFeedback) ordinaryFeedback.textContent = "";
    active = {detail, restoreFocus, selection};
    cleanupTimer = window.setTimeout(() => cancel("complete"), config.duration);
  }

  function eventDetail(event) {
    const detail = event.detail?.value && typeof event.detail.value === "object"
      ? event.detail.value : event.detail;
    return detail && typeof detail === "object" ? detail : null;
  }

  let lastAuthoritativeContext = currentContext();
  maxGameplayElapsedMs = lastAuthoritativeContext?.gameplayElapsedMs || 0;

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    const form = event.detail.elt?.matches?.("form")
      ? event.detail.elt : event.detail.elt?.closest?.("form");
    const path = form?.getAttribute("action") || "";
    const canCreateRoutine = form?.matches(".answer-form:not(.challenge-answer-form)")
      || ["/purchase-hint/", "/purchase-reverse/", "/skip/"].some(
        (suffix) => path.endsWith(suffix)
      );
    const requestId = canCreateRoutine
      ? form?.querySelector('input[name="request_id"]')?.value : null;
    if (requestId) {
      actionEpochs.set(requestId, interruptionEpoch);
      if (actionEpochs.size > 32) {
        actionEpochs.delete(actionEpochs.keys().next().value);
      }
    }
  });

  document.body.addEventListener("routineFeedbackConfirmed", (event) => {
    const detail = eventDetail(event);
    if (!detail?.eventId || seenEventIds.has(detail.eventId)) return;
    seenEventIds.add(detail.eventId);
    const requestEpoch = actionEpochs.get(detail.actionId);
    actionEpochs.delete(detail.actionId);
    if (requestEpoch !== interruptionEpoch) return;
    if (Number(detail.state?.gameplayElapsedMs) < maxGameplayElapsedMs) return;
    if (!feedback[detail.kind] || !isCurrent(detail) || hasHigherPrioritySurface()) return;
    start(detail);
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (event.detail.target?.id !== "game-status") return;
    const current = currentContext();
    if (current?.runId !== lastAuthoritativeContext?.runId) {
      interruptionEpoch += 1;
      maxGameplayElapsedMs = current?.gameplayElapsedMs || 0;
    } else {
      maxGameplayElapsedMs = Math.max(
        maxGameplayElapsedMs,
        current?.gameplayElapsedMs || 0,
      );
    }
    if (
      current?.runId === lastAuthoritativeContext?.runId
      && !contextHasTakeover(lastAuthoritativeContext)
      && contextHasTakeover(current)
    ) {
      interruptionEpoch += 1;
    }
    lastAuthoritativeContext = current;
    if (active && (!isCurrent(active.detail) || hasHigherPrioritySurface())) {
      cancel("takeover");
    }
  });

  document.body.addEventListener("htmx:oobAfterSwap", (event) => {
    if (event.detail.target?.id !== "gameplay-event") return;
    const eventId = event.detail.target?.dataset?.eventId;
    if (eventId && eventId !== lastGameplayInterruptionId) {
      lastGameplayInterruptionId = eventId;
      interruptionEpoch += 1;
    }
    if (active) cancel("gameplay-event");
  });

  new MutationObserver((records) => {
    const hasGameplayEvent = records.some((record) => Array.from(record.addedNodes).some(
      (node) => node.nodeType === 1 && (
        node.matches?.("#gameplay-event[data-event-id]")
        || node.querySelector?.("#gameplay-event[data-event-id]")
      )
    ));
    if (hasGameplayEvent) {
      const eventId = document.querySelector("#gameplay-event[data-event-id]")?.dataset.eventId;
      if (eventId && eventId !== lastGameplayInterruptionId) {
        lastGameplayInterruptionId = eventId;
        interruptionEpoch += 1;
      }
      if (active) cancel("gameplay-event");
    }
  }).observe(document.body, {childList: true, subtree: true});

  window.addEventListener("pagehide", () => cancel("navigation"));
}());
