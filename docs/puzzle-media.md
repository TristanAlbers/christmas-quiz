# Normal Advent puzzle media

Normal Advent puzzles may contain private images, private audio, or a mixture of both. Media remains declarative package data and is pinned into the immutable run snapshot at Start.

## Authoring contract

The existing string form remains supported and continues to mean an image:

```json
"media": ["a/clue.png"]
```

New content can use explicit typed entries:

```json
"media": [
  {
    "type": "image",
    "path": "a/clue.png",
    "alt": "Rode kerstster met drie witte stippen"
  },
  {
    "type": "audio",
    "path": "a/clue.mp3"
  }
]
```

Supported normal-puzzle media types are:

- `image`: requires `path`; optional non-empty `alt` text is recommended for meaningful images;
- `audio`: requires only `type` and `path`.

Legacy string and typed entries may be mixed in the same `media` list. A legacy string is always interpreted as an image; the application does not guess presentation type from the filename extension.

This is a backwards-compatible extension of the current package contract and does not require a package schema-version bump. Existing schema-v6 packages with string media remain valid unchanged.

## Playback and presentation

Normal puzzle audio is a team-device clue, not central Music Quiz playback.

- Audio is rendered with a manual native play/replay control.
- It never autoplays merely because a puzzle appears or a 500 ms poll occurs.
- While the same puzzle context remains current, normal polling does not recreate the audio control, so an in-progress native playback interaction is not reset by polling.
- Changing to a different authoritative puzzle may replace the question pane and therefore the old audio control.

Central Music Quiz audio remains governed separately by `docs/music-audio-playback.md`.

## Privacy and snapshots

Typed media uses the existing private puzzle-media boundary. The media `type` is presentation metadata only and never grants access.

A normal puzzle asset is served only when all existing checks pass, including:

- the request is authenticated as the team named by the private route;
- the requested run is the active Advent run;
- the team is currently allowed to view its puzzle;
- the asset belongs to that team's current puzzle;
- the asset exists in the immutable run snapshot.

Team A therefore cannot fetch Team B media, and future puzzle media remains unavailable until that puzzle becomes current.

All existing package-media filesystem guarantees remain in force: paths must be safe relative paths, referenced files may not traverse through symlinks, and the existing 20 MB per-asset limit is unchanged. Source-package edits after Start do not change media served for the active run.

## Scope boundary

This typed form applies to normal Advent puzzle `media`. Challenge media remains on its existing contract, and Music Quiz tracks continue to use the dedicated Music `audio` field and central-TV playback flow.
