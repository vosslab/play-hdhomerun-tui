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
