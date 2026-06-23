"""Tests for tuner.playback.build_command profile selection (pure, offline).

Only the progressive-vs-interlaced flag profile is covered here, since the mpv
flags matter and are easy to change by accident.  Live behavior -- mediainfo
probing and the detached mpv launch -- is verified manually, not in pytest.
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
