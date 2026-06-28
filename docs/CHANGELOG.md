## 2026-06-26

### Behavior or Interface Changes

- `probe_format` now runs `ffprobe` instead of `mediainfo` to detect stream
  format. It reads the first video stream's `field_order` (`progressive` -> p,
  `tt`/`bb`/`tb`/`bt` -> i) and `height`, with a bounded `-read_intervals
  '%+#1'` sample and a 12 s timeout. Live verification: `2.1` -> `1080i`,
  `7.1` -> `720p`.
- Brewfile now requires `ffmpeg` (provides `ffprobe`) in place of `mediainfo`.

### Fixes and Maintenance

- Fixed the always-blank Format column. `mediainfo` never reaches end-of-file
  on a continuous HDHomeRun transport stream, so the probe hung until its
  timeout fired and always returned an empty label; nothing was ever cached
  (`cache.json` `"format"` stayed `{}`). A hung `mediainfo` process also held a
  tuner open, which produced HTTP 503 lockouts. Persistence and rendering were
  already correct; only the probe was broken.

### Decisions and Failures

- Chose `ffprobe` over `mediainfo` for the format probe. `mediainfo` is fine for
  finite files but cannot probe a never-ending live stream; `ffprobe` with a
  bounded read interval returns in seconds and reports `field_order` and
  `height` directly.

### Developer Tests and Notes

- `pytest tests/test_playback.py` passes (8 tests). `probe_format` itself
  remains covered by manual E2E against the live device, not pytest.

## 2026-06-24

### Additions and New Features

- Add `tests/e2e/e2e_tui_screenshot.py`: an offline Textual pilot harness that renders the TUI with a synthetic 86-channel lineup at 100x30 and 80x24, exports SVG frames, and asserts the channel list rendered, the footer tokens (`refresh`/`quit`) are on the bottom row, and the alias-popup footer swap works. Runs fully offline by stubbing `tuner.discover.discover_devices` and `tuner.lineup.fetch_channels` and pointing `HOME` at a temp dir so no device and no real config/cache files are touched.
- Add `docs/screenshots/tui_100x30.svg` and `docs/screenshots/tui_80x24.svg`: curated TUI screenshots referenced from `README.md`.
- Add a Screenshots section to `README.md` and to `docs/USAGE.md` documenting the harness run command and the `output_smoke/` scratch vs `docs/screenshots/` curated split.
- Add a `REPO_HYGIENE_FILTERS` entry in `tests/conftest.py` excluding `docs/screenshots/**` from file-discovery hygiene tests; the SVG assets contain non-ASCII scrollbar and box glyphs by nature.
- Document the new `tests/e2e/` runner and the committed `docs/screenshots/` directory in `docs/FILE_STRUCTURE.md`, and reference the screenshot harness from `docs/CODE_ARCHITECTURE.md`.

### Behavior or Interface Changes

- Dock the keybinding-hint footer to the bottom edge (`dock: bottom` in `HDHRApp.CSS`) so it stays pinned to the bottom row regardless of channel-list length. Only the footer is docked; the status line and column header stay in normal flow, because Textual overlaps multiple widgets docked to the same edge.

### Fixes and Maintenance

- Fix the keybinding-hint footer not displaying. Two compounding causes: (1) the undocked `Static#footer` was pushed below the viewport by the long channel list; (2) `height: 1` combined with `border-top` left zero rows for text under Textual's border-box sizing, so even an on-screen footer rendered blank. Fix: add `dock: bottom` and set `height: 2` on `#footer` (one row for the border separator, one for the help text).
- Ignore the scratch `output_smoke/` screenshot dump via `.gitignore` (`output_*`); the committed copies live in `docs/screenshots/`.

### Decisions and Failures

- Keep the hand-rolled `Static#footer` and dock it rather than adopting Textual's built-in `Footer`. The curated hints `up/down` and `Enter/p` are not real `BINDINGS` (they come from `ListView`-native motion and the `ListView.Selected` message), so the built-in widget would silently drop them and change the styling.
- Root-cause learning: the missing footer was a layout bug, not missing text. A zero-height content row from `height: 1` plus `border-top` made the docked footer invisible until the height was raised to 2. The new screenshot harness guards both the docking and the visible height at the 80x24 minimum size.

### Developer Tests and Notes

- The screenshot harness is the regression witness for the footer; run it with `source source_me.sh && python3 tests/e2e/e2e_tui_screenshot.py`. `pytest tests/` stays the fast lane (532 tests pass).
- Make `tests/e2e/e2e_tui_screenshot.py` directly executable (shebang plus exec bit) and report failures by raising `SystemExit`, matching the repo convention for runnable scripts.

## 2026-06-23

### Additions and New Features

- Add `docs/CODE_ARCHITECTURE.md`: system design, component descriptions, primary data flow from launch to mpv playback, testing overview, extension points, and known gaps.
- Add `docs/FILE_STRUCTURE.md`: directory map with per-file purpose, subtree breakdowns for `tuner/`, `tests/`, `docs/`, and `devel/`, generated artifact table, and a where-to-add-new-work reference.
- Update `README.md` Documentation section to link `docs/CODE_ARCHITECTURE.md` and `docs/FILE_STRUCTURE.md`.

- Add `docs/INSTALL.md`: setup steps covering Homebrew system deps (`python@3.12`, `mpv`, `mediainfo`), pip deps (`textual`, `requests`), and a verify-install command.
- Add `docs/TROUBLESHOOTING.md`: failure modes grounded in real code behavior -- discovery failure with `--host` recovery, mpv not installed, mediainfo not installed (Format stays blank, playback falls back to `KNOWN_INTERLACED_GUIDE_NUMBERS`), and how to reset state (cache vs. preferences files separately or together).

- Add `tuner/` package with `models.py`: `Device` and `Channel` dataclasses; `Channel.sort_key` sorts by numeric `GuideNumber`.
- Add `tuner/discover.py`: HTTP discover.json fetch at `hdhomerun.local` first; pure-Python UDP broadcast fallback on port 65001; CRC computed via stdlib `binascii`.
- Add `tuner/lineup.py`: fetch and parse `lineup.json` from device into a `Channel` list.
- Add `tuner/state.py` with two backing files behind one `State` facade: `~/.config/play-hdhomerun-tui/preferences.json` (version, favorites_seeded_from_device, favorites, aliases) and `~/.cache/play-hdhomerun-tui/cache.json` (version, play_counts, last_played, format). Constructor accepts overridable `prefs_path` and `cache_path` for tests.
- Add `alias(guide_number)` and `set_alias(guide_number, label)` to `State`; empty label clears the alias key; persisted to preferences.
- Add `set_format(guide_number, label)` and `format_label(guide_number) -> str | None` to `State`; replaces the old boolean interlace map.
- Add `probe_format(url, guide_number) -> str` to `tuner/playback.py`; runs `mediainfo` and returns a short label such as `1080i`, `720p`, `1080p`, or `480i`; returns empty string on any failure so the display stays blank rather than showing a guessed label.
- Add `interlaced_from_format(label) -> bool` to `tuner/playback.py`; pure helper returning True when a non-empty label ends in `i`.
- Add `interlace_for_playback(label, guide_number) -> bool` to `tuner/playback.py`; uses `interlaced_from_format(label)` when label is non-empty, otherwise falls back to `KNOWN_INTERLACED_GUIDE_NUMBERS`. The old `is_interlaced` is removed; callers use `probe_format` plus `interlace_for_playback` directly.
- Add `tuner/playback.py`: `build_command` reproduces mpv tuning flags; detached `Popen` launch.
- Add `tuner/app.py`: modeless Textual list with wide fixed-column table and a persistent dim column header. `render_channel_row` accepts `is_cursor`, `name_width`, `alias_width`, `alias_label`, `format_label`, and `play_count`; columns are cursor, Fav, Ch, Alias, Name, Format, Quality, Strength, Plays.
- Add pure helpers to `tuner/app.py`: `name_width_for_channels(channels, cap)`, `_pad_text(text, width)`, `_num_cell(value, width)`, `_remaining_name_width(major_width)`, and `column_header_line(major_width, name_width, alias_width)`.
- Add persistent column-header `Static` (`#col_header`) above `#channel_list` in `compose()`; rebuilt after lineup load, refresh, and favorite toggle.
- Add physical `>` cursor: `_repaint_cursor()` repaints every visible channel row on highlight change; no full-width bar.
- Add `AliasPopup` (`ModalScreen`): small modal prefilled with the current alias; Enter saves via `state.set_alias`; Esc cancels; submitting empty clears the alias. After save the list re-renders and the highlight stays on the same channel. While open, list bindings do not fire; the footer switches to `Enter save   Esc cancel`.
- Add `a` binding to `HDHRApp.BINDINGS` and `action_alias` method: opens `AliasPopup` for the highlighted channel; no-op on section headers or empty list.
- Add `_FOOTER_MAIN` and `_FOOTER_ALIAS` constants with Rich markup: arrow glyphs via unicode escapes (source stays ASCII), key tokens `[bold cyan]`-colored, action labels `[dim]`.
- Add `import textual.containers` and `import textual.screen` for `Container` and `ModalScreen`.
- Add `hdhr_tui.py` launcher: thin entry point with `--host` option for device hostname override.
- Add `README.md` and `docs/USAGE.md` documenting the TUI launcher and wide table interface.
- Add offline unit tests: `tests/test_lineup.py` (fixture parsing), `tests/test_state.py` (two-file split, seeding, override, reload, alias set/clear, prune, sort_blocks two-group via tmp_path), `tests/test_playback.py` (mpv command profiles, interlaced_from_format mapping, interlace_for_playback blank-label fallback), `tests/test_app_helpers.py` (dot-justified guide formatting, _pad_text pad/truncate, _num_cell right-align and blank). Renamed from `tests/test_app_format.py` via `git mv`.

### Behavior or Interface Changes

- Rewrite `README.md` lead paragraph (the GitHub About source) in plainer language: drop jargon (Textual, TUI, OTA, LAN, mpv, detached) for a 234-char prose description that keeps the auto-discovery, favorites/history, and dual-channel-viewing selling points.
- `prune_to_lineup(channels)` prunes only cache maps (play_counts, last_played, format); preferences (favorites, aliases) survive a transient lineup gap and are never pruned.
- `sort_blocks(channels)` returns two groups `(favorites, all_channels)` in stable numeric order; the play-count-ordered Frequent block is removed. Play counts are still tracked and shown in the Plays column.
- Saving is file-targeted: a favorites toggle or alias edit writes preferences only; a selection or format write touches the cache only.
- Signal quality and strength are never stored in either file; they are live readings only.
- Suppress the default ListView full-width highlight bar (`#channel_list > ListItem.-highlight` and the focused variant) by setting `background: transparent`, `color: $foreground`, and `text-style: none`; the `>` cursor glyph is the only selection indicator.
- Add `.block-header { color: $text-muted; }` so section headers read as dim labels.
- Update `#footer` with a `border-top: solid $panel-lighten-1` for subtle chrome with `background: $panel`.
- Add `KeyboardLaunchListView` (a `ListView` subclass) for the channel list: a mouse click moves the highlight but no longer posts `Selected`, so clicks never launch a channel. Launching is keyboard-only (Enter or `p`), preventing accidental playback from a stray click or double-click.

### Fixes and Maintenance

- Fix header/row column misalignment in `tuner/app.py`: define `_FAV_WIDTH = 3` and `_SEP = " "` as shared constants; both `column_header_line` and `render_channel_row` now join cells with `_SEP.join([...])` using the same ordered cell list. `_remaining_name_width` counts 9 columns and 8 separators.

### Removals and Deprecations

- Remove the Frequent block from `sort_blocks`; the return type is now a 2-tuple instead of a 3-tuple.
- Remove `set_interlace` and `interlace_verdict` methods from `State`; replaced by `set_format` and `format_label`.
- Remove `format_reception` helper from `tuner/app.py` (old `Q80/S63` inline field); replaced by separate Quality and Strength columns in the wide table.
- Remove the HD column from channel rows; `Format` carries resolution/scan detail instead.
- Rename `tests/test_app_format.py` to `tests/test_app_helpers.py` via `git mv`; new file covers `_pad_text` and `_num_cell` helpers in addition to the existing guide-number formatting tests.

### Decisions and Failures

- Storage split by meaning: user choices (favorites, aliases) in `~/.config`; disposable derived data (play counts, last played, format labels) in `~/.cache`. Cache is safe to delete without losing preferences.
- One-time storage reset on first run after this change: the old single `state.json` is superseded by two new files. Favorites re-seed from the device `Favorite:1`, aliases start empty, play counts and format labels rebuild as channels are used. No migration shim; data is low-value and self-rebuilding.
- Format fills in lazily as channels are launched; the lineup is never probed up front on load.
- Keep `ListView` (not `DataTable`): `DataTable` cannot give non-selectable, cursor-skipped section rows; `ListView`'s disabled `ListItem`s already support them. Wide table is built with fixed-width string formatting in pure helpers so layout is unit-testable without the TUI.
- Discovery order: `--host` flag first, then HTTP at `hdhomerun.local`, then UDP fallback; device-specific IDs stay out of committed code and are supplied privately via `--host`.
- CRC uses stdlib `binascii`; `crcmod` is not required.
- FLEX DUO has two tuners (two concurrent streams allowed); the launcher does not enforce a concurrency limit.
- Pytest scope is intentionally small: pure offline logic only. Discovery (HTTP/UDP), mediainfo probing, and live mpv playback are verified by manual E2E, not mocked pytest. When in doubt, the test is deleted rather than mocked.
- No TUI channel demote: the HDHomeRun web UI hides channels; the launcher does not replicate that.

### Developer Tests and Notes

- Full test suite: 522 tests passing (offline, sub-second).
- Python deps: `textual`, `requests` (pip); system deps: `mpv`, `mediainfo` (brew).
- Manual macOS window and E2E gate (live device, mpv window) remains for the user to confirm.
