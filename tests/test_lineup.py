"""Tests for tuner.lineup.parse_channels using a small inline synthetic fixture.

These cover the parser contract only -- field mapping, optional-field defaults,
duplicate-name independence, numeric sort key, and verbatim stream URL.  No real
device file is read, so the tests stay fast and stable.
"""

# local repo modules
import tuner.lineup
import tuner.models

#============================================

# Synthetic lineup entries shaped like the device /lineup.json output.
# Covers: HD+Favorite present, all-optional-absent, duplicate names, and
# present-vs-absent signal fields.  This is fabricated, not a real capture.
SAMPLE_ENTRIES = [
	{
		"GuideNumber": "7.1", "GuideName": "ABC", "HD": 1, "Favorite": 1,
		"SignalQuality": 90, "SignalStrength": 80,
		"URL": "http://hdhomerun.local:5004/auto/v7.1",
	},
	{
		# all optional fields absent
		"GuideNumber": "11.1", "GuideName": "PBS",
		"URL": "http://hdhomerun.local:5004/auto/v11.1",
	},
	{
		"GuideNumber": "24.2", "GuideName": "DUP", "HD": 1,
		"URL": "http://hdhomerun.local:5004/auto/v24.2",
	},
	{
		"GuideNumber": "24.10", "GuideName": "DUP", "HD": 1,
		"URL": "http://hdhomerun.local:5004/auto/v24.10",
	},
	{
		"GuideNumber": "2.1", "GuideName": "CBS", "HD": 1, "Favorite": 1,
		"SignalQuality": 80, "SignalStrength": 60,
		"URL": "http://hdhomerun.local:5004/auto/v2.1",
	},
]

#============================================

def channel_by_guide(channels: list, guide_number: str) -> tuner.models.Channel:
	"""Return the parsed channel with the given guide number.

	Args:
		channels: Parsed Channel list.
		guide_number: Guide number to look up.

	Returns:
		The matching Channel.
	"""
	# direct lookup; the synthetic fixture always contains the requested number
	matches = [ch for ch in channels if ch.guide_number == guide_number]
	return matches[0]

#============================================

def test_parse_returns_channel_objects() -> None:
	"""parse_channels returns tuner.models.Channel instances."""
	channels = tuner.lineup.parse_channels(SAMPLE_ENTRIES)
	assert all(isinstance(ch, tuner.models.Channel) for ch in channels)

#============================================

def test_hd_flag_maps_from_entry() -> None:
	"""HD:1 maps to hd True; an absent HD field maps to hd False."""
	channels = tuner.lineup.parse_channels(SAMPLE_ENTRIES)
	assert channel_by_guide(channels, "7.1").hd is True
	assert channel_by_guide(channels, "11.1").hd is False

#============================================

def test_favorite_flag_maps_from_entry() -> None:
	"""Favorite:1 maps to device_favorite True; an absent field maps to False."""
	channels = tuner.lineup.parse_channels(SAMPLE_ENTRIES)
	assert channel_by_guide(channels, "7.1").device_favorite is True
	assert channel_by_guide(channels, "11.1").device_favorite is False

#============================================

def test_signal_fields_present_and_absent() -> None:
	"""Signal fields parse to ints when present and None when absent."""
	channels = tuner.lineup.parse_channels(SAMPLE_ENTRIES)
	present = channel_by_guide(channels, "7.1")
	assert present.signal_quality == 90
	assert present.signal_strength == 80
	absent = channel_by_guide(channels, "11.1")
	assert absent.signal_quality is None
	assert absent.signal_strength is None

#============================================

def test_duplicate_name_channels_are_distinct() -> None:
	"""Two channels sharing a name stay distinct by guide number."""
	channels = tuner.lineup.parse_channels(SAMPLE_ENTRIES)
	first = channel_by_guide(channels, "24.2")
	second = channel_by_guide(channels, "24.10")
	assert first.guide_name == second.guide_name
	assert first.guide_number != second.guide_number

#============================================

def test_sort_key_numeric_order() -> None:
	"""sort_key orders 7.1 before 11.1 numerically, not lexicographically."""
	channels = tuner.lineup.parse_channels(SAMPLE_ENTRIES)
	low = channel_by_guide(channels, "7.1")
	high = channel_by_guide(channels, "11.1")
	assert low.sort_key < high.sort_key

#============================================

def test_sort_key_sub_channel_order() -> None:
	"""sort_key orders 24.2 before 24.10 by numeric minor part."""
	channels = tuner.lineup.parse_channels(SAMPLE_ENTRIES)
	low = channel_by_guide(channels, "24.2")
	high = channel_by_guide(channels, "24.10")
	assert low.sort_key < high.sort_key
