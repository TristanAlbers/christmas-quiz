(() => {
  "use strict";

  const liveOverview = document.getElementById("live-overview");
  const panel = document.getElementById("overview-audio-player");
  const player = document.getElementById("music-player");
  const heading = document.getElementById("music-audio-heading");
  const message = document.getElementById("music-audio-message");
  const action = document.getElementById("music-audio-action");
  const volume = document.getElementById("music-audio-volume");

  if (!liveOverview || !panel || !player || !heading || !message || !action || !volume) {
    return;
  }

  let stateNode = document.getElementById("overview-audio-state");
  let armed = false;
  let sourceKey = "";
  let playGeneration = 0;
  let soundCheckGeneration = 0;
  let checkingSound = false;
  let soundCheckTimer = null;
  let soundCheckSaved = null;

  player.volume = Number(volume.value);

  function currentState() {
    const node = document.getElementById("overview-audio-state");
    if (!node) {
      return {
        globalState: "",
        phase: "",
        questionNumber: "",
        audioUrl: "",
        runId: "",
      };
    }
    return {
      globalState: node.dataset.globalState || "",
      phase: node.dataset.musicPhase || "",
      questionNumber: node.dataset.questionNumber || "",
      audioUrl: node.dataset.audioUrl || "",
      runId: node.dataset.runId || "",
    };
  }

  function isActiveMusicQuestion(state) {
    return (
      state.globalState === "MUSIC_QUIZ" &&
      state.phase === "question" &&
      Boolean(state.questionNumber)
    );
  }

  function isPausedMusicQuestion(state) {
    return (
      state.globalState === "PAUSED" &&
      state.phase === "question" &&
      Boolean(state.questionNumber)
    );
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

  function setNotEnabled(detail = "Enable sound once during setup so Music Quiz tracks can start reliably.") {
    setStatus("not-enabled", "Sound not enabled", detail, "🔔 Enable sound");
  }

  function setReady(detail = "Sound is armed for the TV. Music will start automatically when a track becomes current.") {
    setStatus("ready", "Sound ready", detail, "Test sound");
  }

  function setPlaying() {
    setStatus(
      "playing",
      "Playing",
      "The current Music Quiz track is playing on this TV."
    );
  }

  function setPaused() {
    setStatus(
      "paused",
      "Paused",
      "Music is paused with the game. It will continue from this position when the Game Master resumes.",
      "Test sound"
    );
  }

  function setBlocked() {
    setStatus(
      "blocked",
      "Sound blocked",
      "The browser blocked playback. Click retry to grant sound permission on this TV.",
      "Retry sound"
    );
  }

  function setPlaybackError() {
    setStatus(
      "error",
      "Playback error",
      "The current audio could not be played. Check the TV output and retry; the game itself is still running.",
      "Retry sound"
    );
  }

  function cancelPendingPlay() {
    playGeneration += 1;
  }

  function safeTime() {
    const value = Number(player.currentTime);
    return Number.isFinite(value) && value >= 0 ? value : 0;
  }

  function setTimeWhenPossible(value) {
    const target = Number.isFinite(value) && value >= 0 ? value : 0;
    const apply = () => {
      try {
        player.currentTime = target;
      } catch (_error) {
        // Metadata may not be ready yet. loadedmetadata below gets another chance.
      }
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

  function loadQuestion(state) {
    const desiredKey = `${state.runId}:${state.questionNumber}`;
    if (sourceKey === desiredKey) {
      return;
    }
    cancelPendingPlay();
    player.pause();
    player.loop = true;
    sourceKey = desiredKey;
    player.src = questionSource(state);
    setTimeWhenPossible(0);
    player.load();
  }

  async function playCurrentTrack() {
    if (!player.getAttribute("src")) {
      return;
    }
    const generation = ++playGeneration;
    try {
      await Promise.resolve(player.play());
      if (generation !== playGeneration) {
        return;
      }
      armed = true;
      setPlaying();
    } catch (error) {
      if (generation !== playGeneration) {
        return;
      }
      if (error && error.name === "NotAllowedError") {
        armed = false;
        setBlocked();
      } else {
        setPlaybackError();
      }
    }
  }

  function capturePlayer() {
    return {
      src: player.getAttribute("src") || "",
      time: safeTime(),
      loop: player.loop,
      key: sourceKey,
    };
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
    if (!checkingSound) {
      return;
    }
    checkingSound = false;
    soundCheckGeneration += 1;
    if (soundCheckTimer !== null) {
      window.clearTimeout(soundCheckTimer);
      soundCheckTimer = null;
    }
    player.pause();
    if (restore && soundCheckSaved) {
      restorePlayer(soundCheckSaved);
    }
    soundCheckSaved = null;
  }

  function finishSoundCheck(generation) {
    if (!checkingSound || generation !== soundCheckGeneration) {
      return;
    }
    const saved = soundCheckSaved;
    checkingSound = false;
    soundCheckTimer = null;
    soundCheckSaved = null;
    player.pause();
    if (saved) {
      restorePlayer(saved);
    }
    reconcile();
  }

  async function runSoundCheck() {
    const soundCheckUrl = panel.dataset.soundCheckUrl;
    if (!soundCheckUrl) {
      setPlaybackError();
      return;
    }

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
      if (!checkingSound || generation !== soundCheckGeneration) {
        return;
      }
      armed = true;
      setReady("Sound check passed. This TV is armed for Music Quiz playback.");
      soundCheckTimer = window.setTimeout(() => finishSoundCheck(generation), 650);
    } catch (error) {
      if (!checkingSound || generation !== soundCheckGeneration) {
        return;
      }
      const saved = soundCheckSaved;
      checkingSound = false;
      soundCheckSaved = null;
      player.pause();
      if (saved) {
        restorePlayer(saved);
      }
      if (error && error.name === "NotAllowedError") {
        armed = false;
        setBlocked();
      } else {
        setPlaybackError();
      }
    }
  }

  function reconcile() {
    if (checkingSound) {
      cancelSoundCheck(true);
    }

    const state = currentState();

    if (isPausedMusicQuestion(state)) {
      cancelPendingPlay();
      player.pause();
      if (armed) {
        setPaused();
      } else {
        setNotEnabled("Music is paused. Enable sound now so the TV is ready when the game resumes.");
      }
      return;
    }

    if (!isActiveMusicQuestion(state)) {
      clearPlayer();
      if (armed) {
        setReady();
      } else {
        setNotEnabled();
      }
      return;
    }

    const desiredKey = `${state.runId}:${state.questionNumber}`;
    if (!state.audioUrl) {
      if (sourceKey !== desiredKey) {
        clearPlayer();
        sourceKey = desiredKey;
      }
      if (armed) {
        setReady("Sound is armed. No audio file is packaged for this Music question.");
      } else {
        setNotEnabled("No audio file is packaged for this question, but you can still arm TV sound for later tracks.");
      }
      return;
    }

    loadQuestion(state);
    if (!armed) {
      setNotEnabled("The current track is loaded. Enable sound on this TV to start playback.");
      return;
    }
    void playCurrentTrack();
  }

  action.addEventListener("click", () => {
    const state = currentState();
    if (isActiveMusicQuestion(state) && state.audioUrl) {
      armed = true;
      loadQuestion(state);
      void playCurrentTrack();
      return;
    }
    void runSoundCheck();
  });

  volume.addEventListener("input", () => {
    player.volume = Number(volume.value);
  });

  player.addEventListener("error", () => {
    if (!player.getAttribute("src")) {
      return;
    }
    if (checkingSound) {
      const saved = soundCheckSaved;
      cancelSoundCheck(false);
      if (saved) {
        restorePlayer(saved);
      }
    } else {
      cancelPendingPlay();
      player.pause();
    }
    setPlaybackError();
  });

  const observer = new MutationObserver(() => {
    const nextStateNode = document.getElementById("overview-audio-state");
    if (nextStateNode === stateNode) {
      return;
    }
    stateNode = nextStateNode;
    reconcile();
  });
  observer.observe(liveOverview, { childList: true, subtree: true });

  reconcile();
})();
