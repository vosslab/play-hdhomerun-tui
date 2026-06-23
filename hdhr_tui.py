#!/usr/bin/env python3
"""Thin launcher for the HDHomeRun OTA channel TUI.

Parses the single optional --host escape hatch, then hands off to tuner.app,
where all the TUI logic lives.  The standard path needs no flags: run it and
the app auto-discovers the device, fetches the lineup, and shows the picker.
"""

# Standard Library
import argparse

# local repo modules
import tuner.app

#============================================

def parse_args() -> argparse.Namespace:
	"""Parse command-line arguments.

	Returns:
		The parsed args namespace with a single optional 'host' attribute.
	"""
	parser = argparse.ArgumentParser(
		description="Discover an HDHomeRun and launch OTA channels in mpv."
	)
	parser.add_argument(
		"-H", "--host", dest="host", default=None,
		help="bare hostname or IP of the HDHomeRun (escape hatch for unusual networks)",
	)
	args = parser.parse_args()
	return args

#============================================

def main() -> None:
	"""Parse args and run the TUI."""
	args = parse_args()
	tuner.app.run(host=args.host)

#============================================

if __name__ == '__main__':
	main()
