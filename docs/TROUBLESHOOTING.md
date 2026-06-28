# TROUBLESHOOTING.md

Common failure modes and how to fix them.

## Discovery fails: no HDHomeRun found

**Symptom:** The TUI shows a message like
`Discovery failed: HDHomeRun discovery failed. Attempted: ...`
and lists each method that was tried (HTTP at `hdhomerun.local`, then UDP broadcast).

**Why:** The auto-discovery tries two paths in order:
1. HTTP GET `http://hdhomerun.local/discover.json` (works when the device
   answers the generic mDNS hostname).
2. UDP broadcast on port 65001 (fallback for unusual networks).

Both paths fail when the device is on a different subnet, mDNS is suppressed
by the router, or the device is off.

**Fix:** Pass the device hostname or IP directly with `--host`:

```bash
source source_me.sh && python3 hdhr_tui.py --host <hostname-or-ip>
```

Replace `<hostname-or-ip>` with the device's LAN IP address (visible in your
router's DHCP table or the HDHomeRun setup app) or a resolvable hostname.

---

## mpv not installed

**Symptom:** After pressing Enter on a channel, the status bar shows
`Launch failed: mpv not found - install with: brew install mpv`

**Fix:**

```bash
brew install mpv
```

---

## ffprobe not installed: Format column stays blank

**Symptom:** The Format column shows nothing for every channel even after
launching them.

**Why:** `probe_format` runs `ffprobe` on the stream URL to read `field_order`
and `height`. When `ffprobe` is not found, the subprocess raises
`FileNotFoundError` and `probe_format` returns an empty string. The column
stays blank rather than showing a guessed label.

**Behavior without ffprobe:** Playback still works. The interlace decision
falls back to the hard-coded `KNOWN_INTERLACED_GUIDE_NUMBERS` table (currently
contains channel `2.1` for CBS 1080i). Other channels default to progressive.
The Format column fills in as channels are launched once `ffprobe` is
installed.

**Note:** `mediainfo` cannot be used here. It never reaches end-of-file on a
continuous HDHomeRun transport stream, so the probe hangs until killed and the
label never fills in. `ffprobe` reads a bounded sample and returns in seconds.

**Fix:**

```bash
brew install ffmpeg
```

---

## Resetting play counts and format labels

Delete the cache file. The cache holds play counts, last-played times, and
format labels only. Deleting it does not affect favorites or channel aliases.

```bash
rm ~/.cache/play-hdhomerun-tui/cache.json
```

The file is recreated on the next launch. Play counts reset to zero and the
Format column refills lazily as channels are launched.

---

## Resetting favorites and aliases

Delete the preferences file. This clears all favorites and aliases. On the
next launch, favorites re-seed from the `Favorite:1` flag the device reports
in the lineup.

```bash
rm ~/.config/play-hdhomerun-tui/preferences.json
```

---

## Resetting all state

Delete both files:

```bash
rm ~/.cache/play-hdhomerun-tui/cache.json
rm ~/.config/play-hdhomerun-tui/preferences.json
```

---

## Format column fills slowly

**Expected behavior:** Format labels fill in lazily, one channel at a time, as
you launch each channel. The app never probes the entire lineup on startup
because that would stall the UI for every channel in sequence.

Once a non-empty label is cached it persists across restarts and is not
re-probed. To force a re-probe for a channel, delete the cache file (see
above) and launch the channel again.
