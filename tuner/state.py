"""App-managed state: favorites, play counts, last-played, and interlace cache."""

# Standard Library
import os
import json
import datetime

# local repo modules
import tuner.models

#============================================

# Schema version; bump when fields are added or the structure changes incompatibly
_SCHEMA_VERSION = 1

# Default config directory relative to HOME
_DEFAULT_CONFIG_DIR = ".config/play-hdhomerun-tui"
_DEFAULT_STATE_FILE = "state.json"

#============================================

class State:
	"""Holds and persists per-channel state for the HDHomeRun TUI.

	All data is keyed by GuideNumber string so that look-alike channel names
	(e.g. two channels both named "WPVN-CD") remain independent.

	Schema keys in the JSON file:
	  version                  (int)  schema version, currently 1
	  favorites_seeded_from_device (bool) true after the one-time device seed
	  favorites                (list) sorted list of guide-number strings
	  play_counts              (dict) guide_number -> int
	  last_played              (dict) guide_number -> ISO timestamp string
	  interlace                (dict) guide_number -> bool verdict

	Internally, favorites is kept as a Python set for O(1) membership checks
	and serialized to a sorted list for stable, readable JSON output.
	"""

	def __init__(self, path: str | None = None) -> None:
		"""Initialize State and load existing data from disk.

		Args:
			path: Explicit path to the state JSON file.  When None, defaults to
			      ~/.config/play-hdhomerun-tui/state.json (built via os.environ["HOME"]).
			      Tests pass a path under tmp_path; no env var or CLI flag is used.
		"""
		if path is None:
			# HOME is a standard OS environment variable; allowed per PYTHON_STYLE.md
			home = os.environ["HOME"]
			path = os.path.join(home, _DEFAULT_CONFIG_DIR, _DEFAULT_STATE_FILE)
		self._path = path
		self._load()

	#============================================

	def _empty_data(self) -> dict:
		"""Return a fresh, empty state dict.

		Returns:
			Dict matching the full schema with all collections empty.
		"""
		data = {
			"version": _SCHEMA_VERSION,
			"favorites_seeded_from_device": False,
			"favorites": [],
			"play_counts": {},
			"last_played": {},
			"interlace": {},
		}
		return data

	#============================================

	def _load(self) -> None:
		"""Load state from disk, or start fresh when the file does not exist.

		Missing file -> empty state (not an error).  Keys are accessed directly
		on known-present fields; .get() only for genuinely optional ones.
		"""
		if not os.path.exists(self._path):
			data = self._empty_data()
		else:
			with open(self._path, "r", encoding="utf-8") as fh:
				data = json.load(fh)

		# required fields -- direct access so a corrupt file raises KeyError loudly
		self._favorites_seeded = data["favorites_seeded_from_device"]
		# favorites stored as list in JSON; load into a set for fast membership checks
		self._favorites: set = set(data["favorites"])
		self._play_counts: dict = data["play_counts"]
		self._last_played: dict = data["last_played"]
		self._interlace: dict = data["interlace"]

	#============================================

	def _save(self) -> None:
		"""Persist current state to disk as JSON.

		Creates the config directory on first write.  Writes favorites as a
		sorted list for stable, human-readable output.
		"""
		config_dir = os.path.dirname(self._path)
		# exist_ok=True: harmless if the directory already exists
		os.makedirs(config_dir, exist_ok=True)
		data = {
			"version": _SCHEMA_VERSION,
			"favorites_seeded_from_device": self._favorites_seeded,
			# sorted list for stable JSON across saves
			"favorites": sorted(self._favorites),
			"play_counts": self._play_counts,
			"last_played": self._last_played,
			"interlace": self._interlace,
		}
		with open(self._path, "w", encoding="utf-8") as fh:
			json.dump(data, fh, indent=2)

	#============================================

	def seed_favorites_from_channels(self, channels: list[tuner.models.Channel]) -> None:
		"""One-time seed of favorites from device Favorite flags.

		Runs only when favorites have not yet been seeded; after that the local
		favorites set is authoritative and device Favorite changes are ignored.

		Args:
			channels: Current channel lineup, each with a device_favorite bool.
		"""
		# guard: seed at most once
		if self._favorites_seeded:
			return
		for channel in channels:
			if channel.device_favorite:
				self._favorites.add(channel.guide_number)
		self._favorites_seeded = True
		self._save()

	#============================================

	def prune_to_lineup(self, channels: list[tuner.models.Channel]) -> None:
		"""Remove state entries for channels no longer in the lineup.

		Prunes favorites, play_counts, last_played, and interlace together so
		old channels do not accumulate and the file stays small and current.

		Args:
			channels: Current channel lineup.
		"""
		# build a set of valid guide numbers from the current lineup
		valid_guide_numbers = {ch.guide_number for ch in channels}

		# prune each collection to only the valid guide numbers
		self._favorites = self._favorites & valid_guide_numbers

		for guide_number in list(self._play_counts.keys()):
			if guide_number not in valid_guide_numbers:
				del self._play_counts[guide_number]

		for guide_number in list(self._last_played.keys()):
			if guide_number not in valid_guide_numbers:
				del self._last_played[guide_number]

		for guide_number in list(self._interlace.keys()):
			if guide_number not in valid_guide_numbers:
				del self._interlace[guide_number]

	#============================================

	def record_selection(self, guide_number: str) -> None:
		"""Increment the play count and record last-played timestamp.

		Args:
			guide_number: GuideNumber of the channel that was selected.
		"""
		# increment play count; default to 0 when not yet present (genuinely optional)
		self._play_counts[guide_number] = self._play_counts.get(guide_number, 0) + 1
		# ISO timestamp using local time; sorting must not rely on this value
		self._last_played[guide_number] = datetime.datetime.now().isoformat()
		self._save()

	#============================================

	def toggle_favorite(self, guide_number: str) -> None:
		"""Add or remove a channel from the favorites set.

		Args:
			guide_number: GuideNumber of the channel to toggle.
		"""
		if guide_number in self._favorites:
			self._favorites.discard(guide_number)
		else:
			self._favorites.add(guide_number)
		self._save()

	#============================================

	def set_interlace(self, guide_number: str, verdict: bool) -> None:
		"""Cache the interlace detection verdict for a channel.

		Args:
			guide_number: GuideNumber of the channel.
			verdict: True when the channel is interlaced.
		"""
		self._interlace[guide_number] = verdict
		self._save()

	#============================================

	def interlace_verdict(self, guide_number: str) -> bool | None:
		"""Return the cached interlace verdict for a channel.

		Args:
			guide_number: GuideNumber of the channel.

		Returns:
			The cached bool verdict, or None when no verdict has been cached.
		"""
		# genuinely optional lookup: a channel may have no cached verdict yet
		return self._interlace.get(guide_number)

	#============================================

	def sort_blocks(
		self,
		channels: list[tuner.models.Channel],
	) -> tuple[list[tuner.models.Channel], list[tuner.models.Channel], list[tuner.models.Channel]]:
		"""Partition channels into three ordered blocks for TUI rendering.

		Priority (each channel appears in exactly one block):
		  1. favorites -- sorted by play count descending, then numeric sort_key
		  2. frequent  -- has a play count but is not a favorite; same sort
		  3. all_channels -- remainder (no count, not a favorite); sorted by sort_key

		Numeric sort_key means 7.1 before 11.1, and 24.2 before 24.10.

		Args:
			channels: Full channel lineup to partition.

		Returns:
			Tuple (favorites, frequent, all_channels), each a list of Channel.
		"""
		favorites_list: list[tuner.models.Channel] = []
		frequent_list: list[tuner.models.Channel] = []
		remainder_list: list[tuner.models.Channel] = []

		for channel in channels:
			guide_number = channel.guide_number
			if guide_number in self._favorites:
				favorites_list.append(channel)
			elif self._play_counts.get(guide_number, 0) > 0:
				frequent_list.append(channel)
			else:
				remainder_list.append(channel)

		# sort key for favorites and frequent: count desc, then numeric channel order
		def count_then_sort_key(ch: tuner.models.Channel) -> tuple[int, int, int]:
			count = self._play_counts.get(ch.guide_number, 0)
			major, minor = ch.sort_key
			# negate count so higher counts sort first
			return (-count, major, minor)

		favorites_list.sort(key=count_then_sort_key)
		frequent_list.sort(key=count_then_sort_key)

		# all_channels sorted purely by numeric sort_key
		remainder_list.sort(key=lambda ch: ch.sort_key)

		return (favorites_list, frequent_list, remainder_list)

	#============================================

	@property
	def favorites(self) -> set:
		"""Read-only view of the current favorites set.

		Returns:
			Frozenset of guide-number strings currently marked as favorites.
		"""
		return frozenset(self._favorites)

	#============================================

	@property
	def play_counts(self) -> dict:
		"""Read-only copy of the play-count dict.

		Returns:
			Dict mapping guide_number to int count.
		"""
		return dict(self._play_counts)

	#============================================

	@property
	def favorites_seeded(self) -> bool:
		"""True when the one-time device-seed step has been completed.

		Returns:
			bool indicating whether favorites have been seeded from device data.
		"""
		return self._favorites_seeded
