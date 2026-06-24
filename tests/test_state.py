"""Tests for tuner.state.State using tmp_path for all file I/O.

All I/O is directed to tmp_path via the two-file constructor:
  State(prefs_path=..., cache_path=...).
No network, no real subprocess, no Textual widgets.
"""

# PIP3 modules
import pytest

# local repo modules
import tuner.models
import tuner.state

#============================================

def _make_channel(
	guide_number: str,
	guide_name: str = "Test",
	device_favorite: bool = False,
) -> tuner.models.Channel:
	"""Construct a minimal Channel for state tests.

	Args:
		guide_number: Guide number string, e.g. "2.1".
		guide_name: Channel name string.
		device_favorite: Whether the device marks this channel as favorite.

	Returns:
		A Channel dataclass instance with stub signal/stream fields.
	"""
	return tuner.models.Channel(
		guide_number=guide_number,
		guide_name=guide_name,
		stream_url=f"http://hdhomerun.local:5004/auto/v{guide_number}",
		hd=True,
		device_favorite=device_favorite,
		signal_quality=None,
		signal_strength=None,
	)

#============================================

def _make_state(tmp_path: pytest.TempPathFactory) -> tuner.state.State:
	"""Build a State backed by two tmp_path files.

	Args:
		tmp_path: pytest-supplied temporary directory.

	Returns:
		A fresh State instance writing to tmp_path.
	"""
	prefs_path = str(tmp_path / "preferences.json")
	cache_path = str(tmp_path / "cache.json")
	return tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)

#============================================

def test_first_run_seeds_from_device_favorite(tmp_path: pytest.TempPathFactory) -> None:
	"""First-run seeding copies device Favorite:1 channels into local favorites."""
	state = _make_state(tmp_path)
	channels = [
		_make_channel("2.1", "CBS2-HD", device_favorite=True),
		_make_channel("7.1", "WLS-HD", device_favorite=False),
	]
	state.seed_favorites_from_channels(channels)
	# the device favorite must land in local favorites after seed
	assert "2.1" in state.favorites
	# non-favorite must not appear
	assert "7.1" not in state.favorites

#============================================

def test_seed_runs_only_once(tmp_path: pytest.TempPathFactory) -> None:
	"""A second seed call after seeding does not overwrite local favorites."""
	state = _make_state(tmp_path)
	# first seed: CBS is a device favorite
	state.seed_favorites_from_channels([
		_make_channel("2.1", "CBS2-HD", device_favorite=True),
	])
	# user un-favorites CBS and favorites ABC manually
	state.toggle_favorite("2.1")
	state.toggle_favorite("7.1")
	# second seed attempt with CBS still flagged as device favorite
	state.seed_favorites_from_channels([
		_make_channel("2.1", "CBS2-HD", device_favorite=True),
		_make_channel("7.1", "WLS-HD", device_favorite=False),
	])
	# local favorites must win: CBS removed by user, ABC added by user
	assert "2.1" not in state.favorites
	assert "7.1" in state.favorites

#============================================

def test_favorites_seeded_persists_across_reload(tmp_path: pytest.TempPathFactory) -> None:
	"""favorites_seeded is True after seed and survives a reload from disk."""
	prefs_path = str(tmp_path / "preferences.json")
	cache_path = str(tmp_path / "cache.json")
	state = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	state.seed_favorites_from_channels([_make_channel("2.1", device_favorite=True)])
	# reload from the same files
	state2 = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	assert state2.favorites_seeded is True

#============================================

def test_favorites_land_in_favorites_block(tmp_path: pytest.TempPathFactory) -> None:
	"""Favorited channels land in the favorites block returned by sort_blocks."""
	state = _make_state(tmp_path)
	cbs = _make_channel("2.1", "CBS2-HD")
	abc = _make_channel("7.1", "WLS-HD")
	state.toggle_favorite("2.1")
	favorites, all_channels = state.sort_blocks([cbs, abc])
	fav_numbers = {ch.guide_number for ch in favorites}
	# favorited channel must appear in favorites block
	assert "2.1" in fav_numbers
	# non-favorited channel must not appear in favorites block
	assert "7.1" not in fav_numbers

#============================================

def test_all_channels_numeric_order(tmp_path: pytest.TempPathFactory) -> None:
	"""All-channels block sorts numerically: 7.1 before 11.1."""
	state = _make_state(tmp_path)
	ch_7 = _make_channel("7.1")
	ch_11 = _make_channel("11.1")
	# feed them in reversed order to prove sorting works
	_favorites, all_channels = state.sort_blocks([ch_11, ch_7])
	guide_numbers = [ch.guide_number for ch in all_channels]
	assert guide_numbers.index("7.1") < guide_numbers.index("11.1")

#============================================

def test_sub_channel_numeric_order(tmp_path: pytest.TempPathFactory) -> None:
	"""All-channels block puts 24.2 before 24.10 (numeric, not lexicographic)."""
	state = _make_state(tmp_path)
	ch_24_2 = _make_channel("24.2", "WPVN-CD")
	ch_24_10 = _make_channel("24.10", "WPVN-CD")
	# insert reversed to verify sort
	_favorites, all_channels = state.sort_blocks([ch_24_10, ch_24_2])
	guide_numbers = [ch.guide_number for ch in all_channels]
	assert guide_numbers.index("24.2") < guide_numbers.index("24.10")

#============================================

def test_duplicate_name_channels_favorited_independently(tmp_path: pytest.TempPathFactory) -> None:
	"""Two channels with the same guide name but different guide numbers are independent."""
	state = _make_state(tmp_path)
	# both channels are named WPVN-CD; only 24.2 gets favorited
	ch_24_2 = _make_channel("24.2", "WPVN-CD")
	ch_24_10 = _make_channel("24.10", "WPVN-CD")
	state.toggle_favorite("24.2")
	favorites, all_channels = state.sort_blocks([ch_24_2, ch_24_10])
	fav_numbers = {ch.guide_number for ch in favorites}
	all_numbers = {ch.guide_number for ch in all_channels}
	assert "24.2" in fav_numbers
	assert "24.10" in all_numbers

#============================================

def test_toggle_favorite_removes_existing(tmp_path: pytest.TempPathFactory) -> None:
	"""A second toggle_favorite removes a channel from the favorites set."""
	state = _make_state(tmp_path)
	state.toggle_favorite("2.1")
	assert "2.1" in state.favorites
	state.toggle_favorite("2.1")
	assert "2.1" not in state.favorites

#============================================

def test_format_set_get_round_trip_across_reload(tmp_path: pytest.TempPathFactory) -> None:
	"""set_format persists the label and a fresh load returns the same value."""
	prefs_path = str(tmp_path / "preferences.json")
	cache_path = str(tmp_path / "cache.json")
	state = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	state.set_format("2.1", "1080i")
	# reload from the same cache file
	state2 = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	assert state2.format_label("2.1") == "1080i"

#============================================

def test_alias_set_then_clear_round_trip_across_reload(tmp_path: pytest.TempPathFactory) -> None:
	"""set_alias with a value persists; set_alias with empty clears and reload shows None."""
	prefs_path = str(tmp_path / "preferences.json")
	cache_path = str(tmp_path / "cache.json")
	state = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	# set an alias and confirm it persists
	state.set_alias("7.1", "ABC")
	state2 = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	assert state2.alias("7.1") == "ABC"
	# clear the alias with an empty string
	state2.set_alias("7.1", "")
	state3 = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	assert state3.alias("7.1") is None

#============================================

def test_prune_drops_stale_cache_entries(tmp_path: pytest.TempPathFactory) -> None:
	"""prune_to_lineup removes play counts and format for channels no longer in the lineup."""
	prefs_path = str(tmp_path / "preferences.json")
	cache_path = str(tmp_path / "cache.json")
	state = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	# record data for two channels
	state.record_selection("2.1")
	state.set_format("2.1", "1080i")
	state.record_selection("7.1")
	# prune the lineup to only 2.1; 7.1 should vanish from cache
	state.prune_to_lineup([_make_channel("2.1")])
	assert "7.1" not in state.play_counts

#============================================

def test_prune_keeps_favorites_and_aliases(tmp_path: pytest.TempPathFactory) -> None:
	"""prune_to_lineup does not remove favorites or aliases for stale channels."""
	prefs_path = str(tmp_path / "preferences.json")
	cache_path = str(tmp_path / "cache.json")
	state = tuner.state.State(prefs_path=prefs_path, cache_path=cache_path)
	# add a favorite and alias for a channel that will leave the lineup
	state.toggle_favorite("7.1")
	state.set_alias("7.1", "ABC")
	# prune the lineup to only 2.1; 7.1 is no longer in the lineup
	state.prune_to_lineup([_make_channel("2.1")])
	# preferences survive the prune
	assert "7.1" in state.favorites
	assert state.alias("7.1") == "ABC"

#============================================

def test_sort_blocks_returns_two_groups(tmp_path: pytest.TempPathFactory) -> None:
	"""sort_blocks returns exactly two groups (favorites, all_channels) in numeric order."""
	state = _make_state(tmp_path)
	ch_2 = _make_channel("2.1", "CBS2-HD")
	ch_7 = _make_channel("7.1", "WLS-HD")
	state.toggle_favorite("2.1")
	# unpacking into two names is the real contract: a 3-tuple would raise here
	favorites, all_channels = state.sort_blocks([ch_2, ch_7])
	# 2.1 is in favorites; 7.1 is in all_channels
	assert any(ch.guide_number == "2.1" for ch in favorites)
	assert any(ch.guide_number == "7.1" for ch in all_channels)
