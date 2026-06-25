# Code architecture

Zero-config Textual TUI that discovers an HDHomeRun OTA tuner on the LAN,
lists channels with favorites and play history, and launches mpv detached.

## Overview

The app is a single-process Python 3.12 program. On startup it discovers the
HDHomeRun device, fetches the channel lineup, and renders a fixed-column channel
picker. Network work and mpv probing run in Textual worker threads so the UI
stays responsive at all times.

Entry point: [hdhr_tui.py](../hdhr_tui.py)
TUI package: [tuner/](../tuner/)
Runtime dependencies: `textual` (TUI), `requests` (HTTP to device)
System dependencies: `mpv` (video player), `mediainfo` (stream format probe)

## Major components

### Entry point -- hdhr_tui.py

Thin launcher. Parses the single optional `--host` flag and hands off to
`tuner.app.run()`. Contains no TUI logic.

### tuner/models.py

Shared dataclasses:

- `Device` -- discovered HDHomeRun device (base URL, lineup URL, device id, IP).
- `Channel` -- single OTA channel (guide number, guide name, stream URL, HD flag,
  device-favorite flag, signal quality, signal strength, numeric sort key).

No external dependencies. All other modules import from here.

### tuner/discover.py

Resolves a `Device` from the LAN. Three methods tried in order, first success wins:

1. Explicit `--host` hostname or IP (HTTP GET `/discover.json`).
2. HTTP GET `http://hdhomerun.local/discover.json` (primary, no install required).
3. UDP broadcast on port 65001 (Silicondust protocol, stdlib only, no extra dep).

Public entry: `discover_devices(host=None) -> Device`.

### tuner/lineup.py

Fetches and parses the channel list from a `Device`. Sends HTTP GET to
`<device.base_url>/lineup.json` and parses the JSON entries into `Channel`
objects. Parsing is split into a pure `parse_channels(entries)` helper so unit
tests can supply fixture data without a real network request.

### tuner/state.py

Holds and persists per-channel user state behind a single `State` facade.
Data is split into two backing files:

- Preferences (`~/.config/play-hdhomerun-tui/preferences.json`) -- user choices
  that survive lineup changes: `favorites` (list of guide numbers), `aliases`
  (guide number to label map), `favorites_seeded_from_device` (one-time seed flag).
- Cache (`~/.cache/play-hdhomerun-tui/cache.json`) -- app-derived data that
  rebuilds automatically: `play_counts`, `last_played` (ISO timestamp), `format`
  (cached stream format label such as "1080i" or "720p").

All data is keyed by guide-number string (not channel name) so channels with
identical names remain independent. Signal quality and strength are live readings
only and are never written to disk. Cache entries are pruned to the current lineup
on each startup; preferences (favorites, aliases) are never pruned.

### tuner/playback.py

Handles stream format detection and mpv launch.

- `probe_format(url, guide_number)` -- runs `mediainfo --Output=JSON` on the
  stream URL (6 s timeout), reads `Video.ScanType` and `Video.Height`, and
  returns a label such as "1080i" or "720p". Returns empty string on any failure.
- `interlace_for_playback(label, guide_number)` -- derives the interlace flag
  for mpv. Uses the cached label when available; falls back to a hard-coded
  `KNOWN_INTERLACED_GUIDE_NUMBERS` table (e.g. CBS 2.1) when the label is empty.
- `launch(channel, interlaced)` -- builds the mpv command and spawns it detached
  (`start_new_session=True`, all stdio closed). Non-blocking; the TUI returns
  immediately. Two tuners can stream concurrently.

### tuner/app.py

The Textual `App` subclass and all row-rendering helpers.

UI layout (top to bottom): status line, dim column header, `ListView`, footer
help bar. The channel list is a wide fixed-column table (max 100 chars wide)
with columns: cursor (`>`), Fav (`*`), Ch (dot-justified guide number), Alias,
Name, Format, Quality, Strength, Plays.

Channels are sorted into two blocks -- Favorites first, then All channels --
each sorted numerically by guide number. Block headers are non-selectable.

Network work (discover + lineup fetch, lineup refresh) and mpv probing run in
`@textual.work(thread=True)` worker threads. UI updates are marshalled back with
`call_from_thread`. Format labels are cached in state and the probe runs once per
channel on first launch.

`AliasPopup` is a `ModalScreen` that owns the keyboard while open; main-list
keys do not fire until it dismisses.

Module-level helpers (`format_guide_number`, `render_channel_row`,
`column_header_line`) are pure functions so they are testable without
instantiating the app.

## Data flow

The primary use case from launch to playback:

```
hdhr_tui.py
  |
  +- parse_args()           parse --host flag
  +- tuner.app.run()
       |
       +- HDHRApp.__init__  construct app
       +- on_mount          kick off worker thread
            |
            +- _load_device_and_lineup()      [worker thread]
                 |
                 +- tuner.discover.discover_devices(host)
                 |    |
                 |    +- HTTP GET hdhomerun.local/discover.json  [primary]
                 |    +- UDP broadcast port 65001                [fallback]
                 |
                 +- tuner.lineup.fetch_channels(device)
                 |    |
                 |    +- HTTP GET <device.base_url>/lineup.json
                 |
                 +- tuner.state.State()
                 |    |
                 |    +- load preferences.json  (~/.config/...)
                 |    +- load cache.json        (~/.cache/...)
                 |    +- seed_favorites_from_channels  [once only]
                 |    +- prune_to_lineup
                 |
                 +- call_from_thread(_on_lineup_ready)   [main thread]
                      |
                      +- _render_blocks        sort favorites / all channels
                      +- _rebuild_header       update column header line
                      +- _repaint_cursor       paint ">" on first row

  [user presses Enter / p]
       |
       +- action_play()
            |
            +- state.record_selection()          increment play count
            +- _probe_and_launch()               [worker thread]
                 |
                 +- state.format_label()          check cache
                 +- tuner.playback.probe_format() [if not cached]
                 |    |
                 |    +- mediainfo --Output=JSON <stream_url>
                 +- state.set_format()            cache the label
                 +- tuner.playback.interlace_for_playback()
                 +- tuner.playback.launch()
                      |
                      +- subprocess.Popen(mpv ..., start_new_session=True)
```

## Testing and verification

Fast unit tests live in [tests/](../tests/) and run with `pytest tests/`.

Key test files:

- [tests/test_lineup.py](../tests/test_lineup.py) -- `parse_channels` with fixture data.
- [tests/test_state.py](../tests/test_state.py) -- `State` favorites, aliases, counts, pruning.
- [tests/test_playback.py](../tests/test_playback.py) -- format label, interlace decision, command build.
- [tests/test_app_helpers.py](../tests/test_app_helpers.py) -- row rendering and column helpers.
- [tests/test_pyflakes_code_lint.py](../tests/test_pyflakes_code_lint.py) -- pyflakes lint gate.
- [tests/test_function_typing.py](../tests/test_function_typing.py) -- every `def` carries full type annotations.
- [tests/test_markdown_links.py](../tests/test_markdown_links.py) -- every local Markdown link resolves.

Slow or network-dependent tests are not in `pytest tests/`. End-to-end runners
belong in `tests/e2e/` per [docs/E2E_TESTS.md](E2E_TESTS.md); for example
[tests/e2e/e2e_tui_screenshot.py](../tests/e2e/e2e_tui_screenshot.py) renders the
TUI offline and asserts the footer stays on the bottom row.

## Extension points

- Add a new discovery method: extend `tuner/discover.py`, adding a new attempt
  block in `discover_devices()`.
- Add a new persistent state field: add to `_empty_prefs()` or `_empty_cache()`,
  bump `_SCHEMA_VERSION`, and add accessor / mutator methods to `State`.
- Add a new column to the channel table: update the fixed-width constants and
  `render_channel_row()` / `column_header_line()` in `tuner/app.py`.
- Add a key binding: declare a `Binding` in `HDHRApp.BINDINGS` and add an
  `action_<name>()` method.

## Known gaps

- Schema migration: `State` loads files written at `_SCHEMA_VERSION = 1` without
  any migration path. Adding fields with a version bump would require a migration
  step; none exists yet.
- Error recovery: discovery failure shows a status message but the user must
  restart the app or pass `--host` to retry; there is no in-app retry action.
