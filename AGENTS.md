## Coding style

- docs/PYTHON_STYLE.md
- docs/MARKDOWN_STYLE.md
- docs/REPO_STYLE.md
- When making edits, document them in docs/CHANGELOG.md.

## Project docs

- docs/CODE_ARCHITECTURE.md -- system design and components
- docs/FILE_STRUCTURE.md -- directory map and what belongs where
- docs/INSTALL.md -- setup steps and dependencies
- docs/USAGE.md -- how to run the tool and CLI examples

## Python environment

AI agents must run Python using `source source_me.sh && python3` (Python 3.12 only).
Homebrew Python 3.12 site-packages: `/opt/homebrew/lib/python3.12/site-packages/`.

## Tests

- `pytest tests/` for fast unit and integration tests
- See docs/PYTEST_STYLE.md for test rules and failure triage.
- See docs/E2E_TESTS.md for slow end-to-end tests (not run via pytest).
