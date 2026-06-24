# play-hdhomerun-tui

Zero-config Textual TUI for HDHomeRun OTA tuners: auto-discovers the device on your LAN, lists channels with favorites and play history, and launches mpv detached so you can watch both tuners at once.

## Documentation

- [docs/INSTALL.md](docs/INSTALL.md): prerequisites, install steps, and verify command.
- [docs/USAGE.md](docs/USAGE.md): run command, key bindings, and channel list layout.
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md): common failures and how to recover.
- [docs/CODE_ARCHITECTURE.md](docs/CODE_ARCHITECTURE.md): system design, components, and data flow.
- [docs/FILE_STRUCTURE.md](docs/FILE_STRUCTURE.md): directory map and where to add new work.
- [docs/PYTHON_STYLE.md](docs/PYTHON_STYLE.md): Python coding conventions for this repo.
- [docs/REPO_STYLE.md](docs/REPO_STYLE.md): repo-wide organization and workflow rules.

## Quick start

Prerequisites: pip packages `textual` and `requests`; system packages `mpv` and `mediainfo`.

```bash
source source_me.sh && python3 hdhr_tui.py
```

If the device does not answer `hdhomerun.local`, pass a hostname or IP directly:

```bash
source source_me.sh && python3 hdhr_tui.py --host <hostname-or-ip>
```

Arrow keys to pick a channel, Enter to play. See [docs/USAGE.md](docs/USAGE.md) for the full key map.
