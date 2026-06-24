"""App-managed state: a preferences file (favorites, aliases) and a disposable cache file."""

# Standard Library
import os
import json
import datetime

# local repo modules
import tuner.models

#============================================

# Schema version; bump when fields are added or the structure changes incompatibly
_SCHEMA_VERSION = 1

# Default preferences file path relative to HOME (.config is the XDG config home)
_DEFAULT_PREFS_DIR = ".config/play-hdhomerun-tui"
_DEFAULT_PREFS_FILE = "preferences.json"

# Default cache file path relative to HOME (.cache is the XDG cache home)
_DEFAULT_CACHE_DIR = ".cache/play-hdhomerun-tui"
_DEFAULT_CACHE_FILE = "cache.json"

#============================================

class State:
	"""Holds and persists per-channel state for the HDHomeRun TUI.

	All data is keyed by GuideNumber string so that look-alike channel names
	(e.g. two channels both named "WPVN-CD") remain independent.

	Two backing files behind one facade:

	Preferences file -- ~/.config/play-hdhomerun-tui/preferences.json
	  version                      (int)  schema version
	  favorites_seeded_from_device (bool) true after the one-time device seed
	  favorites                    (list) sorted list of guide-number strings
	  aliases                      (dict) guide_number -> label string

	Cache file -- ~/.cache/play-hdhomerun-tui/cache.json
	  version      (int)  schema version
	  play_counts  (dict) guide_number -> int
	  last_played  (dict) guide_number -> ISO timestamp string
	  format       (dict) guide_number -> format-label string (e.g. "1080i", "720p")

	Internally, favorites is kept as a Python set for O(1) membership checks
	and serialized to a sorted list for stable, readable JSON output.

	Signal quality and strength are never stored; they are live readings only.
	"""

	def __init__(
		self,
		prefs_path: str | None = None,
		cache_path: str | None = None,
	) -> None:
		"""Initialize State and load existing data from disk.

		Args:
			prefs_path: Explicit path to the preferences JSON file. When None,
			            defaults to ~/.config/play-hdhomerun-tui/preferences.json
			            built via os.environ["HOME"]. Tests pass a tmp_path.
			cache_path: Explicit path to the cache JSON file. When None, defaults
			            to ~/.cache/play-hdhomerun-tui/cache.json built via
			            os.environ["HOME"]. Tests pass a tmp_path.
		"""
		# HOME is a standard OS environment variable; allowed per PYTHON_STYLE.md
		home = os.environ["HOME"]
		if prefs_path is None:
			prefs_path = os.path.join(home, _DEFAULT_PREFS_DIR, _DEFAULT_PREFS_FILE)
		if cache_path is None:
			cache_path = os.path.join(home, _DEFAULT_CACHE_DIR, _DEFAULT_CACHE_FILE)
		self._prefs_path = prefs_path
		self._cache_path = cache_path
		self._load_prefs()
		self._load_cache()

	#============================================

	def _empty_prefs(self) -> dict:
		"""Return a fresh, empty preferences dict.

		Returns:
			Dict matching the preferences schema with all collections empty.
		"""
		data = {
			"version": _SCHEMA_VERSION,
			"favorites_seeded_from_device": False,
			"favorites": [],
			"aliases": {},
		}
		return data

	#============================================

	def _empty_cache(self) -> dict:
		"""Return a fresh, empty cache dict.

		Returns:
			Dict matching the cache schema with all collections empty.
		"""
		data = {
			"version": _SCHEMA_VERSION,
			"play_counts": {},
			"last_played": {},
			"format": {},
		}
		return data

	#============================================

	def _load_prefs(self) -> None:
		"""Load preferences from disk, or start fresh when the file does not exist.

		Missing file -> empty preferences (not an error). Keys are accessed directly
		on known-present fields; .get() only for genuinely optional ones.
		"""
		if not os.path.exists(self._prefs_path):
			data = self._empty_prefs()
		else:
			with open(self._prefs_path, "r", encoding="utf-8") as fh:
				data = json.load(fh)

		# required fields -- direct access so a corrupt file raises KeyError loudly
		self._favorites_seeded: bool = data["favorites_seeded_from_device"]
		# favorites stored as list in JSON; load into a set for fast membership checks
		self._favorites: set = set(data["favorites"])
		self._aliases: dict = data["aliases"]

	#============================================

	def _load_cache(self) -> None:
		"""Load cache from disk, or start fresh when the file does not exist.

		Missing file -> empty cache (not an error). Keys are accessed directly
		on known-present fields.
		"""
		if not os.path.exists(self._cache_path):
			data = self._empty_cache()
		else:
			with open(self._cache_path, "r", encoding="utf-8") as fh:
				data = json.load(fh)

		# required fields -- direct access so a corrupt file raises KeyError loudly
		self._play_counts: dict = data["play_counts"]
		self._last_played: dict = data["last_played"]
		self._format: dict = data["format"]

	#============================================

	def _save_prefs(self) -> None:
		"""Persist current preferences to disk as JSON.

		Creates the config directory on first write. Writes favorites as a
		sorted list for stable, human-readable output.
		"""
		prefs_dir = os.path.dirname(self._prefs_path)
		# exist_ok=True: harmless if the directory already exists
		os.makedirs(prefs_dir, exist_ok=True)
		data = {
			"version": _SCHEMA_VERSION,
			"favorites_seeded_from_device": self._favorites_seeded,
			# sorted list for stable JSON across saves
			"favorites": sorted(self._favorites),
			"aliases": self._aliases,
		}
		with open(self._prefs_path, "w", encoding="utf-8") as fh:
			json.dump(data, fh, indent=2)

	#============================================

	def _save_cache(self) -> None:
		"""Persist current cache to disk as JSON.

		Creates the cache directory on first write.
		"""
		cache_dir = os.path.dirname(self._cache_path)
		# exist_ok=True: harmless if the directory already exists
		os.makedirs(cache_dir, exist_ok=True)
		data = {
			"version": _SCHEMA_VERSION,
			"play_counts": self._play_counts,
			"last_played": self._last_played,
			"format": self._format,
		}
		with open(self._cache_path, "w", encoding="utf-8") as fh:
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
		self._save_prefs()

	#============================================

	def prune_to_lineup(self, channels: list[tuner.models.Channel]) -> None:
		"""Remove cache entries for channels no longer in the lineup.

		Prunes only the cache maps (play_counts, last_played, format) so old
		channels do not accumulate. Preferences (favorites, aliases) are kept
		intact across a prune -- they represent user choices and survive a
		transient lineup gap.

		Args:
			channels: Current channel lineup.
		"""
		# build a set of valid guide numbers from the current lineup
		valid_guide_numbers = {ch.guide_number for ch in channels}

		# track whether any entry was removed so we only rewrite the file on change
		changed = False

		# prune cache collections only; preferences (favorites, aliases) stay untouched
		for guide_number in list(self._play_counts.keys()):
			if guide_number not in valid_guide_numbers:
				del self._play_counts[guide_number]
				changed = True

		for guide_number in list(self._last_played.keys()):
			if guide_number not in valid_guide_numbers:
				del self._last_played[guide_number]
				changed = True

		for guide_number in list(self._format.keys()):
			if guide_number not in valid_guide_numbers:
				del self._format[guide_number]
				changed = True

		# persist the pruned cache so stale entries do not linger on disk for
		# read-only sessions that never trigger another cache write
		if changed:
			self._save_cache()

	#============================================

	def record_selection(self, guide_number: str) -> None:
		"""Increment the play count and record last-played timestamp.

		Saves to the cache file (not preferences).

		Args:
			guide_number: GuideNumber of the channel that was selected.
		"""
		# increment play count; default to 0 when not yet present (genuinely optional)
		self._play_counts[guide_number] = self._play_counts.get(guide_number, 0) + 1
		# ISO timestamp using local time; sorting must not rely on this value
		self._last_played[guide_number] = datetime.datetime.now().isoformat()
		self._save_cache()

	#============================================

	def toggle_favorite(self, guide_number: str) -> None:
		"""Add or remove a channel from the favorites set.

		Saves to the preferences file.

		Args:
			guide_number: GuideNumber of the channel to toggle.
		"""
		if guide_number in self._favorites:
			self._favorites.discard(guide_number)
		else:
			self._favorites.add(guide_number)
		self._save_prefs()

	#============================================

	def set_format(self, guide_number: str, label: str) -> None:
		"""Cache the stream format label for a channel.

		Saves to the cache file. Callers must pass a confident, non-empty label;
		a failed probe should not be cached, so the caller skips this method when
		the probe returns an empty string.

		Args:
			guide_number: GuideNumber of the channel.
			label: Non-empty format label such as "1080i" or "720p".
		"""
		self._format[guide_number] = label
		self._save_cache()

	#============================================

	def format_label(self, guide_number: str) -> str | None:
		"""Return the cached format label for a channel.

		Args:
			guide_number: GuideNumber of the channel.

		Returns:
			The cached label string (e.g. "1080i"), or None when no label has
			been cached yet.
		"""
		# genuinely optional lookup: a channel may not have been probed yet
		return self._format.get(guide_number)

	#============================================

	def alias(self, guide_number: str) -> str | None:
		"""Return the user-set alias label for a channel.

		Args:
			guide_number: GuideNumber of the channel.

		Returns:
			The alias string (e.g. "CBS", "ABC"), or None when no alias is set.
		"""
		# genuinely optional: most channels have no alias
		return self._aliases.get(guide_number)

	#============================================

	def set_alias(self, guide_number: str, label: str) -> None:
		"""Set or clear the alias label for a channel.

		An empty label removes the alias key entirely. Saves to the preferences file.

		Args:
			guide_number: GuideNumber of the channel.
			label: Alias label to set, or empty string to clear.
		"""
		if label:
			self._aliases[guide_number] = label
		else:
			# empty label means clear the alias; .pop with default avoids KeyError
			self._aliases.pop(guide_number, None)
		self._save_prefs()

	#============================================

	def sort_blocks(
		self,
		channels: list[tuner.models.Channel],
	) -> tuple[list[tuner.models.Channel], list[tuner.models.Channel]]:
		"""Partition channels into two ordered blocks for TUI rendering.

		Blocks (each channel appears in exactly one block):
		  1. favorites     -- channels in the favorites set, sorted by sort_key
		  2. all_channels  -- remainder, sorted by sort_key

		Both blocks use stable numeric sort_key order; play counts do not reorder
		rows (they are shown in the Plays column instead).

		Args:
			channels: Full channel lineup to partition.

		Returns:
			Tuple (favorites, all_channels), each a list of Channel sorted
			numerically by Channel.sort_key.
		"""
		favorites_list: list[tuner.models.Channel] = []
		remainder_list: list[tuner.models.Channel] = []

		for channel in channels:
			if channel.guide_number in self._favorites:
				favorites_list.append(channel)
			else:
				remainder_list.append(channel)

		# stable numeric order by sort_key for both blocks
		favorites_list.sort(key=lambda ch: ch.sort_key)
		remainder_list.sort(key=lambda ch: ch.sort_key)

		return (favorites_list, remainder_list)

	#============================================

	@property
	def favorites(self) -> frozenset:
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
