# INSTALL.md

Getting the HDHomeRun TUI set up and ready to run.

"Installed" means the script runs from the repo directory with no additional
packaging step. There is no `pip install` of this repo itself.

## Requirements

- Python 3.12 (pinned; install via Homebrew `python@3.12`)
- pip packages: `textual`, `requests`
- System tools: `mpv` (media player), `mediainfo` (stream format probe)
- macOS with Homebrew (Brewfile tracks all system deps)
- bash shell (required by `source_me.sh`)

## Install steps

1. Clone the repo and enter it:

   ```bash
   git clone <repo-url>
   cd play-hdhomerun-tui
   ```

2. Install system dependencies via Homebrew:

   ```bash
   brew bundle
   ```

   This installs `python@3.12`, `mpv`, and `mediainfo`.

3. Install pip dependencies:

   ```bash
   pip3 install -r pip_requirements.txt
   ```

## Verify install

Run the help flag to confirm the entry point loads without error:

```bash
source source_me.sh && python3 hdhr_tui.py --help
```

Expected output includes the `-H`/`--host` option description. A working
HDHomeRun device on the LAN is not required for this check.

## Known gaps

- No pinned version specified in `pip_requirements.txt`; compatibility with
  future `textual` releases is untested.
- Linux and Windows are not tested; the Brewfile and `source_me.sh` are
  macOS/bash-specific.
