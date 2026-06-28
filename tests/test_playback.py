"""Tests for tuner.playback pure helpers and build_command profile selection.

Covers:
  - build_command progressive vs interlaced flag profiles.
  - interlaced_from_format label mapping (pure, no subprocess).
  - interlace_for_playback blank-label fallback (pure, no subprocess).

probe_format (runs ffprobe) is not tested here; it is verified by manual E2E.
"""

# local repo modules
import tuner.models
import tuner.playback

#============================================

def _make_channel() -> tuner.models.Channel:
	"""Build a minimal Channel for build_command tests.

	Returns:
		A Channel dataclass instance.
	"""
	return tuner.models.Channel(
		guide_number="2.1",
		guide_name="CBS",
		stream_url="http://hdhomerun.local:5004/auto/v2.1",
		hd=True,
		device_favorite=False,
		signal_quality=None,
		signal_strength=None,
	)

#============================================

def test_build_command_starts_with_mpv() -> None:
	"""build_command returns a list whose first element is 'mpv'."""
	cmd = tuner.playback.build_command(_make_channel(), interlaced=False)
	assert cmd[0] == "mpv"

#============================================

def test_build_command_progressive_profile() -> None:
	"""Progressive selection includes the progressive flags and omits deinterlace."""
	cmd = tuner.playback.build_command(_make_channel(), interlaced=False)
	assert "--force-seekable=yes" in cmd
	assert "--deinterlace=yes" not in cmd

#============================================

def test_build_command_interlaced_profile() -> None:
	"""Interlaced selection adds deinterlace and omits the progressive-only flags."""
	cmd = tuner.playback.build_command(_make_channel(), interlaced=True)
	assert "--deinterlace=yes" in cmd
	assert "--force-seekable=yes" not in cmd

#============================================

def test_interlaced_from_format_1080i_is_true() -> None:
	"""interlaced_from_format returns True for a label ending in 'i'."""
	assert tuner.playback.interlaced_from_format("1080i") is True

#============================================

def test_interlaced_from_format_720p_is_false() -> None:
	"""interlaced_from_format returns False for a label ending in 'p'."""
	assert tuner.playback.interlaced_from_format("720p") is False

#============================================

def test_interlaced_from_format_empty_is_false() -> None:
	"""interlaced_from_format returns False for an empty label (the failed-probe path)."""
	assert tuner.playback.interlaced_from_format("") is False

#============================================

def test_interlace_for_playback_empty_label_known_interlaced_fallback() -> None:
	"""interlace_for_playback with empty label falls back to the known-interlaced table."""
	# pick a real member of the fallback table rather than hardcoding a guide number
	known = next(iter(tuner.playback.KNOWN_INTERLACED_GUIDE_NUMBERS))
	assert tuner.playback.interlace_for_playback("", known) is True

#============================================

def test_interlace_for_playback_label_wins_over_fallback() -> None:
	"""interlace_for_playback uses the label when non-empty, ignoring the fallback table."""
	# a known-interlaced guide number, but a progressive label should win
	known = next(iter(tuner.playback.KNOWN_INTERLACED_GUIDE_NUMBERS))
	assert tuner.playback.interlace_for_playback("720p", known) is False
