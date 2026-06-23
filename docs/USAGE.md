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
| Up / Down | Move channel highlight |
| Enter | Play highlighted channel |
| p | Play highlighted channel |
| f | Favorite / unfavorite highlighted channel |
| r | Refresh channel lineup from device |
| q | Quit |

A persistent footer at the bottom of the screen shows the main keys:
`Enter/p play | f favorite | r refresh | q quit`

## Channel list layout

Channels appear in three ordered blocks. Each channel sits in exactly one block.

- Favorites: user-pinned channels (toggle with `f`), sorted numerically by guide number.
- Frequent: channels with play history, sorted by play count then guide number.
- All channels: remaining channels in stable device order, sorted numerically.

Empty blocks are hidden. On first run with no history only the All channels block
shows. Favorites are seeded once from the device's own favorites list, then managed
locally with `f`.

Guide numbers are dot-justified so the decimal points align in a column
(for example ` 7.1`, `11.1`, `24.2`, `24.10`). Sorting is numeric, so `7.1`
comes before `11.1` and `24.2` before `24.10`.

Each row shows the guide number, guide name, HD flag, and a live reception field
`Q<quality>/S<strength>` when the device reports those values. The reception field
is color-coded by quality: green for 80 and above, yellow for 60-79, red below 60.
When values are absent the field is blank. These values are display-only and are
never stored.

## Playback

Pressing Enter or `p` checks the stream format (about 6 seconds while `mediainfo`
probes the stream) then opens `mpv` in its own detached window. The TUI stays fully
interactive while the probe runs and returns to the channel list immediately after
launch. The HDHomeRun FLEX DUO has two tuners, so two channels can stream
concurrently -- just press Enter on a second channel while the first is playing.

CBS-style 1080i streams auto-deinterlace. ABC and FOX 720p streams play progressive.
The interlace verdict is cached so the probe runs only once per channel.

Quitting the TUI with `q` leaves any open mpv windows running.

## State file

Favorites, play counts, and the interlace cache are stored in:

```
~/.config/play-hdhomerun-tui/state.json
```

This file is created automatically on first run and updated silently. There is no
manual editing required.
