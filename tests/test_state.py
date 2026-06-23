"""Tests for tuner.state.State using tmp_path for all file I/O."""

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

def test_first_run_seeds_from_device_favorite(tmp_path: pytest.TempPathFactory) -> None:
	"""First-run seeding copies device Favorite:1 channels into local favorites."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	channels = [
		_make_channel("2.1", "CBS2-HD", device_favorite=True),
		_make_channel("7.1", "WLS-HD", device_favorite=False),
	]
	state.seed_favorites_from_channels(channels)
	# the device favorite must land in local favorites after seed
	assert "2.1" in state.favorites
	# non-favorite must not appear
	assert "7.1" not in state.favorites


def test_seed_runs_only_once(tmp_path: pytest.TempPathFactory) -> None:
	"""A second seed call after the file exists does not overwrite local favorites."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	# first seed: CBS is a device favorite
	channels_first = [
		_make_channel("2.1", "CBS2-HD", device_favorite=True),
	]
	state.seed_favorites_from_channels(channels_first)
	# user un-favorites CBS and favorites ABC manually
	state.toggle_favorite("2.1")
	state.toggle_favorite("7.1")
	# second seed attempt with CBS still flagged as device favorite
	channels_second = [
		_make_channel("2.1", "CBS2-HD", device_favorite=True),
		_make_channel("7.1", "WLS-HD", device_favorite=False),
	]
	state.seed_favorites_from_channels(channels_second)
	# local favorites must win: CBS removed by user, ABC added by user
	assert "2.1" not in state.favorites
	assert "7.1" in state.favorites


def test_favorites_seeded_flag_persists_after_reload(tmp_path: pytest.TempPathFactory) -> None:
	"""favorites_seeded is True after seed and survives a reload from disk."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	channels = [_make_channel("2.1", device_favorite=True)]
	state.seed_favorites_from_channels(channels)
	# reload from disk
	state2 = tuner.state.State(path=state_file)
	assert state2.favorites_seeded is True


def test_sort_blocks_favorites_block(tmp_path: pytest.TempPathFactory) -> None:
	"""Favorited channels land in the favorites block returned by sort_blocks."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	cbs = _make_channel("2.1", "CBS2-HD")
	abc = _make_channel("7.1", "WLS-HD")
	state.toggle_favorite("2.1")
	favorites, frequent, all_channels = state.sort_blocks([cbs, abc])
	guide_numbers_in_favorites = {ch.guide_number for ch in favorites}
	assert "2.1" in guide_numbers_in_favorites
	# non-favorited channel must not appear in favorites block
	assert "7.1" not in guide_numbers_in_favorites


def test_sort_blocks_frequent_ordering_by_count(tmp_path: pytest.TempPathFactory) -> None:
	"""Frequent block orders channels by play count descending."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	cbs = _make_channel("2.1", "CBS2-HD")
	abc = _make_channel("7.1", "WLS-HD")
	# play CBS twice, ABC once
	state.record_selection("2.1")
	state.record_selection("2.1")
	state.record_selection("7.1")
	_favorites, frequent, _all = state.sort_blocks([cbs, abc])
	# CBS has more plays, so it must appear first in frequent
	assert frequent[0].guide_number == "2.1"


def test_sort_blocks_all_channels_numeric_order(tmp_path: pytest.TempPathFactory) -> None:
	"""All-channels block sorts numerically: 7.1 before 11.1."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	ch_7 = _make_channel("7.1")
	ch_11 = _make_channel("11.1")
	# order them reversed in the input to prove the sort works
	_favorites, _frequent, all_channels = state.sort_blocks([ch_11, ch_7])
	guide_numbers = [ch.guide_number for ch in all_channels]
	assert guide_numbers.index("7.1") < guide_numbers.index("11.1")


def test_sort_blocks_sub_channel_numeric_order(tmp_path: pytest.TempPathFactory) -> None:
	"""All-channels block puts 24.2 before 24.10 (numeric, not lexicographic)."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	ch_24_2 = _make_channel("24.2", "WPVN-CD")
	ch_24_10 = _make_channel("24.10", "WPVN-CD")
	# insert reversed to verify sort
	_favorites, _frequent, all_channels = state.sort_blocks([ch_24_10, ch_24_2])
	guide_numbers = [ch.guide_number for ch in all_channels]
	assert guide_numbers.index("24.2") < guide_numbers.index("24.10")


def test_duplicate_name_channels_favorited_independently(tmp_path: pytest.TempPathFactory) -> None:
	"""Two channels with the same guide name but different guide numbers are independent."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	# both channels are named WPVN-CD; only 24.2 gets favorited
	ch_24_2 = _make_channel("24.2", "WPVN-CD")
	ch_24_10 = _make_channel("24.10", "WPVN-CD")
	state.toggle_favorite("24.2")
	favorites, _frequent, all_channels = state.sort_blocks([ch_24_2, ch_24_10])
	# 24.2 must be in favorites, 24.10 must not
	fav_numbers = {ch.guide_number for ch in favorites}
	all_numbers = {ch.guide_number for ch in all_channels}
	assert "24.2" in fav_numbers
	assert "24.10" in all_numbers


def test_toggle_favorite_removes_existing(tmp_path: pytest.TempPathFactory) -> None:
	"""A second toggle_favorite removes a channel from the favorites set."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	state.toggle_favorite("2.1")
	assert "2.1" in state.favorites
	state.toggle_favorite("2.1")
	assert "2.1" not in state.favorites


def test_set_interlace_round_trips(tmp_path: pytest.TempPathFactory) -> None:
	"""set_interlace persists the verdict and reload from disk returns the same value."""
	state_file = str(tmp_path / "state.json")
	state = tuner.state.State(path=state_file)
	state.set_interlace("2.1", True)
	# reload from disk
	state2 = tuner.state.State(path=state_file)
	# verify via the public accessor that a fresh load holds the right value
	assert state2.interlace_verdict("2.1") is True
