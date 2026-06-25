# USAGE.md

How to run the HDHomeRun TUI channel picker.

## Running

```bash
source source_me.sh && python3 hdhr_tui.py
```

On startup the app discovers the HDHomeRun device automatically (HTTP first, then
UDP broadcast fallback). No flags or config files are required.

### Options

| Option | Description |
| --- | --- |
| `-H`, `--host <hostname-or-ip>` | Skip discovery and connect to this device directly. Accepts a bare hostname or IP address. Use when the device does not answer `hdhomerun.local`. |

Example:

```bash
source source_me.sh && python3 hdhr_tui.py --host 192.168.1.42
```

## Key bindings

| Key | Action |
| --- | --- |
| Up / Down | Move the `>` cursor |
| Enter | Play highlighted channel |
| p | Play highlighted channel |
| f | Favorite / unfavorite highlighted channel |
| a | Edit the alias label for the highlighted channel |
| r | Refresh channel lineup from device |
| q | Quit |

A persistent colored help bar at the bottom of the screen shows the active keys:

```
up/down move   Enter/p play   f favorite   a alias   r refresh   q quit
```

Key tokens are accent-colored and action labels are dim. While the alias popup is
open, the bar switches to `Enter save   Esc cancel` so inactive list keys are never
shown.

## Mouse

Mouse use is intentionally minimal. A mouse click may move the cursor to a channel
row, but a click never launches a channel. Launching playback is keyboard-only,
through Enter or `p`, so an accidental click or double-click cannot start a stream.

## Channel list layout

The channel list is a wide fixed-column table under a persistent dim header row
that names each column once:

```
       Fav  Ch      Alias   Name                     Format   Quality   Strength   Plays
> *    2.1     CBS     CBS2-HD                        1080i       80         63        12
  *    5.1     NBC     NBC5                            720p      100         83         8
  *    7.1     ABC     WLS-HD                          720p      100         85         6
      24.10            WPVN-CD                                    63         53
      48.1             U TOO                                      50         48
```

Columns, left to right:

- `>` cursor: marks the highlighted row; all other rows show a space. There is no
  full-width highlight bar.
- `Fav`: `*` for favorites, space otherwise.
- `Ch`: guide number, dot-justified so decimal points align (`7.1`, `11.1`,
  `24.2`, `24.10`). Sorting is numeric, not lexicographic.
- `Alias`: short user label from preferences (`CBS`, `ABC`), blank when unset.
- `Name`: device guide name, truncated to the available column width.
- `Format`: cached stream format label (`720p`, `1080i`), blank until the channel
  is launched for the first time. Format is filled in lazily as channels are used;
  the lineup is never probed up front.
- `Quality`: live signal quality, bare right-aligned number, subtly color-coded
  (green >= 80, yellow 60-79, red < 60), blank when absent. Never stored.
- `Strength`: live signal strength, bare right-aligned number, blank when absent.
  Never stored.
- `Plays`: play count from the cache, blank when zero.

The table stays under 100 columns so rows never wrap in a standard terminal. Long
names are truncated to fit the name column.

### Channel blocks

Channels appear in two ordered blocks. Each channel sits in exactly one block.

- Favorites: user-pinned channels (toggle with `f`), sorted numerically by guide number.
- All channels: all other channels, sorted numerically by guide number.

Empty blocks are hidden. On first run with no favorites only the All channels block
shows. Favorites are seeded once from the device's own favorites list, then managed
locally with `f`.

Section headers (`Favorites`, `All channels`) are dim and non-selectable; the
cursor skips them.

## Alias editing

Pressing `a` on a highlighted channel opens a small modal popup for editing the
alias label of that channel. The input is prefilled with the current alias (empty
if none). Press Enter to save, or Esc to cancel. Saving an empty value clears the
alias. After saving, the Alias cell updates immediately and the cursor stays on
the same channel. While the popup is open, `q` does not quit the app.

## Playback

Pressing Enter or `p` checks the stream format (about 6 seconds while `mediainfo`
probes the stream the first time) then opens `mpv` in its own detached window.
The TUI stays fully interactive while the probe runs and returns to the channel
list immediately after launch. The HDHomeRun FLEX DUO has two tuners, so two
channels can stream concurrently.

CBS-style 1080i streams auto-deinterlace. ABC and FOX 720p streams play progressive.
The format label is cached so the probe runs only once per channel; the Format
column shows the cached value on subsequent visits.

Quitting the TUI with `q` leaves any open mpv windows running.

## Storage

State is split into two files by purpose.

### Preferences -- ~/.config/play-hdhomerun-tui/preferences.json

Stores user choices that are never auto-deleted:

- `favorites`: list of guide numbers pinned by the user.
- `aliases`: map of guide number to alias label.
- `favorites_seeded_from_device`: flag that the one-time device seed has run.

Preferences survive lineup changes, device reboots, and cache deletion. Favorites
and aliases are never pruned.

### Cache -- ~/.cache/play-hdhomerun-tui/cache.json

Stores app-derived data that rebuilds automatically:

- `play_counts`: how many times each channel has been launched.
- `last_played`: ISO timestamp of the most recent launch.
- `format`: cached stream format label (`1080i`, `720p`) filled in on first launch.

The cache is pruned to the current lineup on each startup. It is safe to delete
`cache.json` at any time -- doing so resets Plays and Format columns back to blank
without affecting favorites or aliases. Favorites and aliases are not touched.

Signal quality and strength are never written to either file; they are live readings
only.

## Screenshots

The offline screenshot harness renders the TUI with a synthetic lineup and checks
that the keybinding-hint footer stays on the bottom row at 100x30 and 80x24:

```bash
source source_me.sh && python3 tests/e2e/e2e_tui_screenshot.py
```

It writes SVG frames into the scratch `output_smoke/` directory. The curated copies
shown in [README.md](../README.md) live in `docs/screenshots/`.
