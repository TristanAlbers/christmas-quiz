# Music Quiz TV audio

The public `/overview/` page is the central playback device for packaged Music Quiz audio. It keeps one `HTMLAudioElement` mounted for the lifetime of the page; HTMX polling updates only declarative playback state, so normal 500 ms refreshes do not recreate the player or restart a track.

## Preparing event audio

Each Music question may set its existing `audio` field to a package-relative local file. For the Christmas event, **MP3 (`audio/mpeg`) is the supported baseline format** because it is broadly supported by current browsers and works with the existing single-file Music question contract.

Audio is part of the game package and is copied into the immutable run snapshot at Start. Keep every referenced media file within the existing **20 MB per-asset limit**. Playback does not require an internet connection, streaming account, or third-party service.

Example:

```json
{
  "id": "music-1",
  "number": 1,
  "title": "Music 1",
  "body": "Name the song.",
  "validator": {"type": "text_exact", "answer": "jingle bells"},
  "audio": "music/jingle-bells.mp3"
}
```

## Operator sound check

When the Music Quiz's 60-second gathering countdown appears:

1. Keep the public TV overview open on the browser connected to the room audio.
2. On the **Music Quiz TV screen**, use **Geluid inschakelen** to authorize playback.
3. Confirm that the short local chime is audible and the panel reports **Geluid klaar**.
4. Set the room volume using the same Music Quiz control.

The TV audio/volume panel is **not shown in READY, Advent, Challenge, non-Music Pause, or final Advent results**. No pre-arming control exists in the normal Advent calendar view. The single audio element is still mounted and stable outside the HTMX-swapped state, even while its controls are hidden.

The permission is browser-page-local. Reloading the overview resets the player page and can require a new click during Music gathering, or the Music question if already active. The normal browser autoplay restriction remains in force.

During Music:
- **Playing** means the current question track is playing and looping.
- Game Master Pause changes the panel to **Paused** and keeps the local playhead. Resuming the same question continues from that position while the page remains loaded.
- A new Music question changes the source on the same media element, resets it to the beginning, and starts playback.
- Final Music results, return to Advent, Ready, and Reset stop and clear the Music track.
- **Sound blocked** or **Playback error** never changes scoring or game state. Use the visible retry action; Game Master Pause remains available if the operator needs time to fix the room audio.

The browser controller appends a question token such as `?q=2` only so the same run-based URL is reloaded when the authoritative question changes. The server does not trust that token: `/music/audio/<run_id>/` still resolves media solely from the active run and current Music question.

## Scope boundary

This document covers central Music Quiz playback only. Normal Advent puzzle audio remains a separate #9 follow-up: its package contract needs typed image/audio media plus a private, manual team playback UI. Legacy generic puzzle media remains image-oriented until that follow-up lands.
