(() => {
  "use strict";

  const liveOverview = document.getElementById("live-overview");
  const panel = document.getElementById("overview-audio-player");
  const player = document.getElementById("music-player");
  const heading = document.getElementById("music-audio-heading");
  const message = document.getElementById("music-audio-message");
  const action = document.getElementById("music-audio-action");
  const volume = document.getElementById("music-audio-volume");

  if (!liveOverview || !panel || !player || !heading || !message || !action || !volume) return;

  let armed = false;
  let sourceKey = "";
  let stateSignature = "";
  let playGeneration = 0;
  let soundCheckGeneration = 0;
  let checkingSound = false;
  let soundCheckTimer = null;
  let soundCheckSaved = null;

  player.volume = Number(volume.value);

  // The player must stay outside the 500ms HTMX fragment. Align the
  // persistent controls with the real reserved row in the Advent layout.
  function positionAdventAudio() {
    const slot = document.getElementById("advent-audio-slot");
    const surface = panel.closest(".public-overview");
    if (!slot || !surface || window.getComputedStyle(slot).display === "none") return;
    const target = slot.getBoundingClientRect();
    const host = surface.getBoundingClientRect();
    const controls = panel.getBoundingClientRect();
    panel.style.setProperty(
      "--advent-audio-top",
      `${Math.round(target.top - host.top - surface.clientTop + (target.height - controls.height) / 2)}px`
    );
    panel.style.setProperty(
      "--advent-audio-right",
      `${Math.round(host.right - target.right - (parseFloat(window.getComputedStyle(surface).borderRightWidth) || 0))}px`
    );
  }

  function currentState() {
    const node = document.getElementById("overview-audio-state");
    if (!node) return { globalState: "", phase: "", questionNumber: "", audioUrl: "", runId: "" };
    return {
      globalState: node.dataset.globalState || "",
      phase: node.dataset.musicPhase || "",
      questionNumber: node.dataset.questionNumber || "",
      audioUrl: node.dataset.audioUrl || "",
      runId: node.dataset.runId || "",
    };
  }

  function signatureFor(state) {
    return [state.runId, state.globalState, state.phase, state.questionNumber, state.audioUrl].join("|");
  }

  function isActiveMusicQuestion(state) {
    return state.globalState === "MUSIC_QUIZ" && state.phase === "question" && Boolean(state.questionNumber);
  }

  function isPausedMusicQuestion(state) {
    return state.globalState === "PAUSED" && state.phase === "question" && Boolean(state.questionNumber);
  }

  function setStatus(kind, title, detail, actionLabel = "") {
    panel.dataset.soundState = kind;
    heading.textContent = title;
    message.textContent = detail;
    if (actionLabel) {
      action.textContent = actionLabel;
      action.hidden = false;
    } else {
      action.hidden = true;
    }
  }

  function setNotEnabled(detail = "Schakel het geluid tijdens de voorbereiding één keer in, zodat nummers uit de Muziek Quiz betrouwbaar kunnen starten.") {
    setStatus("not-enabled", "Geluid niet ingeschakeld", detail, "Geluid inschakelen");
  }

  function setReady(detail = "Het TV-geluid staat klaar. Muziek start automatisch zodra een nummer actief wordt.") {
    setStatus("ready", "Geluid klaar", detail, "Geluid testen");
  }

  function setPlaying() {
    setStatus("playing", "Speelt af", "Het huidige nummer van de Muziek Quiz speelt op deze TV.");
  }

  function setPaused() {
    setStatus("paused", "Gepauzeerd", "De muziek is samen met het spel gepauzeerd en gaat vanaf dezelfde positie verder zodra de Game Master hervat.", "Geluid testen");
  }

  function setBlocked() {
    setStatus("blocked", "Geluid geblokkeerd", "De browser blokkeerde het afspelen. Klik opnieuw om op deze TV toestemming voor geluid te geven.", "Opnieuw proberen");
  }

  function setPlaybackError() {
    setStatus("error", "Afspeelfout", "De huidige audio kon niet worden afgespeeld. Controleer de TV-uitvoer en probeer opnieuw; het spel zelf loopt door.", "Opnieuw proberen");
  }

  function cancelPendingPlay() { playGeneration += 1; }

  function safeTime() {
    const value = Number(player.currentTime);
    return Number.isFinite(value) && value >= 0 ? value : 0;
  }

  function setTimeWhenPossible(value) {
    const target = Number.isFinite(value) && value >= 0 ? value : 0;
    const apply = () => {
      try { player.currentTime = target; } catch (_error) { /* Metadata may not be ready yet. */ }
    };
    apply();
    player.addEventListener("loadedmetadata", apply, { once: true });
  }

  function clearPlayer() {
    cancelPendingPlay();
    player.pause();
    player.loop = true;
    sourceKey = "";
    player.removeAttribute("src");
    player.load();
  }

  function questionSource(state) {
    const separator = state.audioUrl.includes("?") ? "&" : "?";
    return `${state.audioUrl}${separator}q=${encodeURIComponent(state.questionNumber)}`;
  }

  function loadQuestion(state, force = false) {
    const desiredKey = `${state.runId}:${state.questionNumber}`;
    if (!force && sourceKey === desiredKey) return;
    cancelPendingPlay();
    player.pause();
    player.loop = true;
    sourceKey = desiredKey;
    player.src = questionSource(state);
    setTimeWhenPossible(0);
    player.load();
  }

  async function playCurrentTrack() {
    if (!player.getAttribute("src")) return;
    const generation = ++playGeneration;
    try {
      await Promise.resolve(player.play());
      if (generation !== playGeneration) return;
      armed = true;
      setPlaying();
    } catch (error) {
      if (generation !== playGeneration) return;
      if (error && error.name === "NotAllowedError") {
        armed = false;
        setBlocked();
      } else setPlaybackError();
    }
  }

  function capturePlayer() {
    return { src: player.getAttribute("src") || "", time: safeTime(), loop: player.loop, key: sourceKey };
  }

  function restorePlayer(saved) {
    player.pause();
    sourceKey = saved.key;
    player.loop = saved.loop;
    if (saved.src) {
      player.src = saved.src;
      player.load();
      setTimeWhenPossible(saved.time);
    } else {
      player.removeAttribute("src");
      player.load();
    }
  }

  function cancelSoundCheck(restore = true) {
    if (!checkingSound) return;
    checkingSound = false;
    soundCheckGeneration += 1;
    if (soundCheckTimer !== null) {
      window.clearTimeout(soundCheckTimer);
      soundCheckTimer = null;
    }
    player.pause();
    if (restore && soundCheckSaved) restorePlayer(soundCheckSaved);
    soundCheckSaved = null;
  }

  function finishSoundCheck(generation) {
    if (!checkingSound || generation !== soundCheckGeneration) return;
    const saved = soundCheckSaved;
    checkingSound = false;
    soundCheckTimer = null;
    soundCheckSaved = null;
    player.pause();
    if (saved) restorePlayer(saved);
    reconcile(currentState());
  }

  async function runSoundCheck() {
    const soundCheckUrl = panel.dataset.soundCheckUrl;
    if (!soundCheckUrl) { setPlaybackError(); return; }
    cancelPendingPlay();
    cancelSoundCheck(true);
    const generation = ++soundCheckGeneration;
    soundCheckSaved = capturePlayer();
    checkingSound = true;
    sourceKey = "__soundcheck__";
    player.pause();
    player.loop = false;
    player.src = soundCheckUrl;
    setTimeWhenPossible(0);
    player.load();
    try {
      await Promise.resolve(player.play());
      if (!checkingSound || generation !== soundCheckGeneration) return;
      armed = true;
      setReady("Geluidstest geslaagd. Deze TV staat klaar voor de Muziek Quiz.");
      soundCheckTimer = window.setTimeout(() => finishSoundCheck(generation), 650);
    } catch (error) {
      if (!checkingSound || generation !== soundCheckGeneration) return;
      const saved = soundCheckSaved;
      checkingSound = false;
      soundCheckSaved = null;
      player.pause();
      if (saved) restorePlayer(saved);
      if (error && error.name === "NotAllowedError") { armed = false; setBlocked(); } else setPlaybackError();
    }
  }

  function reconcile(state) {
    if (checkingSound) cancelSoundCheck(true);
    if (isPausedMusicQuestion(state)) {
      cancelPendingPlay();
      player.pause();
      if (armed) setPaused();
      else setNotEnabled("De muziek is gepauzeerd. Schakel het geluid nu in zodat de TV klaarstaat wanneer het spel hervat.");
      return;
    }
    if (!isActiveMusicQuestion(state)) {
      clearPlayer();
      if (armed) setReady(); else setNotEnabled();
      return;
    }
    const desiredKey = `${state.runId}:${state.questionNumber}`;
    if (!state.audioUrl) {
      if (sourceKey !== desiredKey) { clearPlayer(); sourceKey = desiredKey; }
      if (armed) setReady("Het geluid staat klaar. Voor deze muziekvraag is geen audiobestand meegeleverd.");
      else setNotEnabled("Voor deze vraag is geen audiobestand meegeleverd, maar je kunt het TV-geluid alvast inschakelen voor latere nummers.");
      return;
    }
    loadQuestion(state);
    if (!armed) {
      setNotEnabled("Het huidige nummer is geladen. Schakel het geluid op deze TV in om af te spelen.");
      return;
    }
    void playCurrentTrack();
  }

  function syncState(force = false) {
    const state = currentState();
    const nextSignature = signatureFor(state);
    if (!force && nextSignature === stateSignature) return;
    stateSignature = nextSignature;
    reconcile(state);
  }

  action.addEventListener("click", () => {
    const state = currentState();
    if (isActiveMusicQuestion(state) && state.audioUrl) {
      armed = true;
      loadQuestion(state, panel.dataset.soundState === "error");
      void playCurrentTrack();
      return;
    }
    void runSoundCheck();
  });

  volume.addEventListener("input", () => { player.volume = Number(volume.value); });
  player.addEventListener("error", () => {
    if (!player.getAttribute("src")) return;
    if (checkingSound) {
      const saved = soundCheckSaved;
      cancelSoundCheck(false);
      if (saved) restorePlayer(saved);
    } else {
      cancelPendingPlay();
      player.pause();
    }
    sourceKey = "";
    setPlaybackError();
  });

  const observer = new MutationObserver(() => syncState());
  observer.observe(liveOverview, { childList: true, subtree: true });
  liveOverview.addEventListener("htmx:afterSettle", () => {
    syncState();
    positionAdventAudio();
  });
  liveOverview.addEventListener("htmx:oobAfterSwap", () => syncState());
  window.addEventListener("resize", positionAdventAudio);
  syncState(true);
  positionAdventAudio();
})();
