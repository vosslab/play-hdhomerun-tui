#!/usr/bin/env python3
"""Offline TUI screenshot harness for the HDHomeRun launcher.

Renders the Textual app headless with a synthetic 86-channel lineup at the
target size 100x30 and the minimum supported size 80x24, exports each frame to
an SVG, and asserts that the channel list rendered and the keybinding-hint
footer is on the bottom row.  Runs fully offline by stubbing the discovery and
lineup seams and pointing HOME at a temp directory, so no device and no real
config or cache files are touched.

Run it directly (outside pytest, per docs/E2E_TESTS.md):

	source source_me.sh && python3 tests/e2e/e2e_tui_screenshot.py

SVG artifacts are written to the scratch dump output_smoke/tui_100x30.svg and
output_smoke/tui_80x24.svg, overwritten on every run.  The curated copies under
docs/screenshots/ are what README.md references; refresh those by copying the
frames from output_smoke/ when the UI changes.
"""

# Standard Library
import os
import sys
import asyncio
import tempfile

# PIP3 modules
import textual.pilot

# Bootstrap sys.path for the local repo modules below: a script run from
# tests/e2e/ only has its own directory on sys.path and source_me.sh does not
# set PYTHONPATH, so add the tests/ dir (for the canonical repo-root finder)
# and then the repo root (for the tuner package).  The textual import above is
# a pip module and needs none of this.
TESTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TESTS_DIR)

# local repo modules
import file_utils
REPO_ROOT = file_utils.get_repo_root()
sys.path.insert(0, REPO_ROOT)

import tuner.app
import tuner.lineup
import tuner.models
import tuner.discover

# Scratch dump for generated frames, overwritten each run (gitignored).  The
# SVG export is deterministic for a fixed lineup.  To update the README images,
# copy the curated frames from here into docs/screenshots/.
OUTPUT_DIR = "output_smoke"

# Target render size and the minimum supported size, rendered in this order.
SIZES = [(100, 30), (80, 24)]

# Bounded wait for the lineup-loading worker thread to populate the list.
POLL_INTERVAL_SECONDS = 0.05
POLL_TIMEOUT_SECONDS = 5.0

#============================================

def fail(size: tuple[int, int], stage: str, detail: str) -> None:
	"""Print a diagnostic message and exit non-zero.

	Args:
		size: The (cols, rows) terminal size being rendered.
		stage: Short label for the failed check (render, footer, alias).
		detail: Human-readable explanation of the failure.
	"""
	# E2E scripts report failures via stderr plus a non-zero exit code;
	# SystemExit carries the message and sets the exit status in one raise
	message = f"FAIL [{size[0]}x{size[1]}] {stage}: {detail}"
	print(message, file=sys.stderr)
	raise SystemExit(1)

#============================================

def build_entries() -> list[dict]:
	"""Build 86 synthetic lineup entries shaped like the device lineup.json.

	The first entry is the known-name favorite CBS2-HD; the next few are
	favorites and the rest are plain channels.  Every URL uses the
	documentation IP block 192.0.2.x so nothing resolves to a real host.

	Returns:
		A list of 86 raw lineup-entry dicts for tuner.lineup.parse_channels.
	"""
	# a handful of named favorites that mirror a realistic OTA lineup
	favorites = ["CBS2-HD", "NBC5", "WLS-HD", "WGN-CW", "WTTW-HD"]
	entries: list[dict] = []
	for index in range(86):
		# distinct guide numbers: majors 2..., five sub-channels each
		major = 2 + index // 5
		minor = 1 + index % 5
		guide_number = f"{major}.{minor}"
		# first five rows reuse the named favorites; the rest get generated names
		if index < len(favorites):
			guide_name = favorites[index]
			favorite_flag = 1
		else:
			guide_name = f"CH{major}-{minor}"
			favorite_flag = 0
		entry = {
			"GuideNumber": guide_number,
			"GuideName": guide_name,
			"URL": f"http://192.0.2.1:5004/auto/v{guide_number}",
			"HD": 1,
			"Favorite": favorite_flag,
			"SignalQuality": 80,
			"SignalStrength": 63,
		}
		entries.append(entry)
	return entries

#============================================

def build_device() -> tuner.models.Device:
	"""Build a synthetic Device pointing at the documentation IP block.

	The caller installs this device as the discovery-seam return value in main().

	Returns:
		A synthetic Device instance.
	"""
	device = tuner.models.Device(
		friendly_name="HDHomeRun FLEX DUO",
		base_url="http://192.0.2.1",
		lineup_url="http://192.0.2.1/lineup.json",
		device_id="TEST1234",
		ip="192.0.2.1",
	)
	return device

#============================================

async def wait_for_lineup(
	app: tuner.app.HDHRApp,
	pilot: textual.pilot.Pilot,
	size: tuple[int, int],
) -> None:
	"""Wait until the lineup-loading worker populates the visible channel list.

	Args:
		app: The running HDHRApp instance.
		pilot: The Textual Pilot driving the app.
		size: The (cols, rows) size, used only for the timeout message.
	"""
	# poll the populated list with a bounded timeout so a stall fails loudly
	elapsed = 0.0
	while elapsed < POLL_TIMEOUT_SECONDS:
		if len(app._visible_channels) > 0:
			await pilot.pause()
			return
		await asyncio.sleep(POLL_INTERVAL_SECONDS)
		await pilot.pause()
		elapsed += POLL_INTERVAL_SECONDS
	fail(size, "render", f"lineup did not populate within {POLL_TIMEOUT_SECONDS}s")

#============================================

async def render_size(size: tuple[int, int]) -> None:
	"""Render the app at one size, save the SVG, and assert footer visibility.

	Args:
		size: The (cols, rows) terminal size to simulate.
	"""
	app = tuner.app.HDHRApp()
	async with app.run_test(size=size) as pilot:
		await wait_for_lineup(app, pilot, size)
		# export the rendered frame as SVG text for assertions
		svg = app.export_screenshot()
		# persist the artifact under a fixed, overwritten name
		out_path = os.path.join(OUTPUT_DIR, f"tui_{size[0]}x{size[1]}.svg")
		app.save_screenshot(out_path)

		# Assertion 1: the offline TUI rendered a populated list
		if "CBS2-HD" not in svg:
			fail(size, "render", "channel name CBS2-HD missing from SVG")

		# Assertion 2: footer help tokens are on-screen.  At 80x24 the 86-row
		# list overflows, so these tokens render only when the footer is docked
		# to the bottom; their presence is the bottom-row proof.
		if "refresh" not in svg or "quit" not in svg:
			fail(size, "footer", "footer tokens refresh/quit missing from SVG")

		# Assertion 3: the alias-popup footer swap.  The swap exercises one CSS
		# path that does not depend on terminal size, so run it once at the
		# target size rather than doubling the pilot I/O at both sizes.
		if size == (100, 30):
			await pilot.press("a")
			await pilot.pause()
			svg_alias = app.export_screenshot()
			if "cancel" not in svg_alias:
				fail(size, "alias", "alias footer token cancel missing after 'a'")
			await pilot.press("escape")
			await pilot.pause()
			svg_back = app.export_screenshot()
			if "refresh" not in svg_back or "quit" not in svg_back:
				fail(size, "alias", "main footer did not return after Esc")

#============================================

async def run_all() -> None:
	"""Render every configured size in order."""
	for size in SIZES:
		await render_size(size)

#============================================

def main() -> None:
	"""Set up the offline environment and run the screenshot harness."""
	# isolate state: HOME points at a temp dir so State() writes nothing real
	tmp_dir = tempfile.mkdtemp(prefix="hdhr_e2e_")
	os.environ["HOME"] = tmp_dir

	# ensure the artifact directory exists
	os.makedirs(OUTPUT_DIR, exist_ok=True)

	# synthetic device and channels returned by the stubbed seams
	device = build_device()
	channels = tuner.lineup.parse_channels(build_entries())

	# save the real seams and swap in offline stubs the app calls module-qualified
	real_discover = tuner.discover.discover_devices
	real_fetch = tuner.lineup.fetch_channels
	tuner.discover.discover_devices = lambda host=None: device
	tuner.lineup.fetch_channels = lambda dev: channels
	try:
		asyncio.run(run_all())
	finally:
		# restore the real seams regardless of outcome
		tuner.discover.discover_devices = real_discover
		tuner.lineup.fetch_channels = real_fetch

	print("OK: footer visible at 100x30 and 80x24; SVGs written to output_smoke/")

#============================================

if __name__ == '__main__':
	main()
