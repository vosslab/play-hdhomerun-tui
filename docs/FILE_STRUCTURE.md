# File structure

Directory map for the `play-hdhomerun-tui` repository.

## Top-level layout

```text
play-hdhomerun-tui/
+- hdhr_tui.py          entry point: parses --host, calls tuner.app.run()
+- tuner/               TUI package (discover, lineup, state, playback, app)
+- tests/               pytest unit tests and repo-wide lint gates
+- devel/               developer tools (not shipped; not imported by the app)
+- docs/                documentation
+- OTHER_REPOS/         references to sibling repos (not used at runtime)
+- source_me.sh         bootstrap: sets PYTHONPATH and Python env vars
+- pip_requirements.txt runtime pip dependencies (requests, textual)
+- pip_requirements-dev.txt  dev pip dependencies (pytest, pyflakes, bandit, ...)
+- Brewfile             Homebrew system packages (mpv, mediainfo)
+- REPO_TYPE            one-line marker: "python"
+- VERSION              current CalVer version string, synced with pyproject.toml
+- README.md            project purpose, quick start, and doc links
+- AGENTS.md            agent coding instructions and tool constraints
+- CLAUDE.md            Claude Code project instructions (references AGENTS.md)
+- LICENSE.MIT.md       MIT license text
```

## Key subtrees

### tuner/ -- TUI package

```text
tuner/
+- __init__.py          empty (no re-exports)
+- models.py            Device and Channel dataclasses
+- discover.py          HDHomeRun LAN discovery (HTTP + UDP fallback)
+- lineup.py            fetch and parse /lineup.json from the device
+- state.py             State class: favorites, aliases, play counts, format cache
+- app.py               Textual App, row renderer, AliasPopup modal
```

See [docs/CODE_ARCHITECTURE.md](CODE_ARCHITECTURE.md) for component details and data flow.

### tests/ -- fast pytest suite

```text
tests/
+- conftest.py              pytest config; excludes tests/e2e/ and tests/playwright/
+- file_utils.py            shared helper: get_repo_root() via git rev-parse
+- TESTS_README.md          test layout and run instructions
|
+- test_app_helpers.py      row rendering and column-width helpers in tuner/app.py
+- test_lineup.py           parse_channels with fixture data (no network)
+- test_state.py            State favorites, aliases, play counts, pruning
+- test_playback.py         probe_format, interlace_for_playback, build_command
|
+- test_pyflakes_code_lint.py   pyflakes lint gate for all .py files
+- test_function_typing.py      every def carries full type annotations
+- test_import_dot.py           no relative imports anywhere
+- test_import_requirements.py  every third-party import declared in pip_requirements
+- test_import_star.py          no import * anywhere
+- test_indentation.py          tabs used for indentation (not spaces)
+- test_init_files.py           __init__.py files are empty or one-line docstrings
+- test_shebangs.py             shebang and executable-bit consistency
+- test_ascii_compliance.py     source files use ASCII only
+- test_whitespace.py           no trailing whitespace
+- test_markdown_links.py       every local Markdown link resolves on disk
+- test_readme_first_paragraph.py   README first paragraph length check
+- test_bandit_security.py      bandit security lint gate
+- test_pytest_hygiene.py       no test_*.py files under e2e/ or playwright/
|
+- check_ascii_compliance.py*   single-file ASCII check (runnable directly)
+- fix_ascii_compliance.py*     single-file ASCII fix (runnable directly)
+- fix_whitespace.py*           single-file whitespace fix (runnable directly)
```

### docs/ -- documentation

```text
docs/
+- CODE_ARCHITECTURE.md     system design, components, and data flow (this repo)
+- FILE_STRUCTURE.md        directory map and where to add new work (this file)
+- INSTALL.md               prerequisites, install steps, and verify command
+- USAGE.md                 run command, key bindings, and column layout
+- TROUBLESHOOTING.md       common failures and how to recover
+- CHANGELOG.md             chronological change log grouped by date
+- AUTHORS.md               maintainers and contributors
+- PYTEST_STYLE.md          pytest test-writing rules and commands
+- PYTHON_STYLE.md          Python formatting and project conventions
+- REPO_STYLE.md            repo-wide organization and workflow rules
+- MARKDOWN_STYLE.md        Markdown writing rules and formatting conventions
+- E2E_TESTS.md             end-to-end test layout and conventions
+- CLAUDE_HOOK_USAGE_GUIDE.md   Claude Code hook allow/deny reference
```

### devel/ -- developer tools

```text
devel/
+- changelog_lib.py         shared parser/serializer for changelog automation
+- rotate_changelog.py      rotate docs/CHANGELOG.md when it exceeds ~1000 lines
+- query_changelog.py       search changelog by date, category, or keyword
+- commit_changelog.py      draft a seed commit message from changelog bullets
```

## Generated artifacts

| Artifact | Location | Git-ignored |
| --- | --- | --- |
| preferences.json | `~/.config/play-hdhomerun-tui/preferences.json` | n/a (outside repo) |
| cache.json | `~/.cache/play-hdhomerun-tui/cache.json` | n/a (outside repo) |
| `__pycache__/` | next to each .py file | yes |
| `.pyc` bytecode | inside `__pycache__/` | yes |

State files are created on first run. They are outside the repo and never
tracked by git. See [docs/USAGE.md](USAGE.md) for field details.

## Documentation map

| File | Purpose |
| --- | --- |
| [README.md](../README.md) | Project overview and quick start |
| [AGENTS.md](../AGENTS.md) | Agent coding instructions |
| [docs/INSTALL.md](INSTALL.md) | Prerequisites, install steps, and verify command |
| [docs/USAGE.md](USAGE.md) | Run command, key bindings, and column reference |
| [docs/TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common failures and how to recover |
| [docs/CODE_ARCHITECTURE.md](CODE_ARCHITECTURE.md) | Components and data flow |
| [docs/FILE_STRUCTURE.md](FILE_STRUCTURE.md) | This file |
| [docs/CHANGELOG.md](CHANGELOG.md) | Change history |

## Where to add new work

| Kind of work | Location |
| --- | --- |
| New TUI feature or key binding | [tuner/app.py](../tuner/app.py) |
| New discovery method | [tuner/discover.py](../tuner/discover.py) |
| New state field (persisted) | [tuner/state.py](../tuner/state.py) |
| New playback option or flag | [tuner/playback.py](../tuner/playback.py) |
| New channel field | [tuner/models.py](../tuner/models.py) |
| Fast unit tests | `tests/test_*.py` in [tests/](../tests/) |
| End-to-end shell/Python tests | `tests/e2e/` (create if needed) |
| New documentation | `docs/` (SCREAMING_SNAKE_CASE.md) |
| Developer scripts | [devel/](../devel/) |
