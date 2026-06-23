## 2026-06-23

### Additions and New Features

- Add `hdhr_tui.py` launcher: thin entry point with `--host` option for device hostname override.
- Add `tuner/` package with `models.py`: `Device` and `Channel` dataclasses; `Channel.sort_key` sorts by numeric `GuideNumber`.
- Add `tuner/discover.py`: HTTP discover.json fetch at `hdhomerun.local` first; pure-Python UDP broadcast fallback on port 65001; CRC computed via stdlib `binascii`.
- Add `tuner/lineup.py`: fetch and parse `lineup.json` from device into a `Channel` list.
- Add `tuner/state.py`: persist state to `~/.config/play-hdhomerun-tui/state.json`; favorites seeded once from device `Favorite:1` then local toggle wins; tracks `play_counts`, `last_played`, and interlace cache; state pruned to current lineup on load; `sort_blocks` returns Favorites / Frequent / All channel groups.
- Add `tuner/playback.py`: `build_command` reproduces the local example mpv tuning flags verbatim; interlace auto-detect via `mediainfo` `ScanType`, `Height`, and `KNOWN_INTERLACED_GUIDE_NUMBERS`; detached `Popen` launch.
- Add `tuner/app.py`: modeless Textual list with numeric dot-justified guide numbers; live color-coded Q/S reception field; keys Up/Down, Enter/p, f, r, q; interlace probe runs in a background worker thread.
- Add `README.md` and `docs/USAGE.md` documenting the TUI launcher.
- Add offline unit tests: `test_lineup.py` (fixture parsing), `test_state.py` (seeding, override, prune, block sort via tmp_path), `test_playback.py` (mpv command profile selection), `test_app_format.py` (dot-justified guide formatting).

### Decisions and Failures

- Discovery order: `--host` flag first, then HTTP at `hdhomerun.local`, then UDP fallback; device-specific IDs stay out of committed code and are supplied privately via `--host`.
- State file is a single small `state.json` with no append-only log.
- Reception Q/S fields are display-only and never stored in state.
- Pytest scope is intentionally small: pure offline logic only (parsing, sorting, state with tmp_path, mpv command building, guide formatting). Discovery (HTTP/UDP), mediainfo probing, and live mpv playback are verified by manual E2E, not mocked pytest. When in doubt, the test is deleted rather than mocked.
- No TUI channel demote: the HDHomeRun web UI hides channels; the launcher does not replicate that.
- FLEX DUO has two tuners (two concurrent streams allowed); the launcher does not enforce a concurrency limit.

### Developer Tests and Notes

- Full test suite: 493 tests passing (offline, sub-second).
- Python deps: `textual`, `requests` (pip); system deps: `mpv`, `mediainfo` (brew).
- CRC uses stdlib `binascii`; `crcmod` is not required.
- Manual macOS window and E2E gate (live device, mpv window) remains for the user to confirm.
