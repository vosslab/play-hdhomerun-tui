"""Launch mpv for an HDHomeRun OTA channel, with deinterlace auto-detection."""

# Standard Library
import json
import subprocess

# local repo modules
import tuner.models

#============================================
# Height thresholds for OTA resolution classes (1080, 720, 480)
_HEIGHT_1080 = 1000
_HEIGHT_720 = 700
_HEIGHT_480 = 400

# mpv flags shared by all profiles (both progressive and interlaced)
SHARED_FLAGS: list[str] = [
	'--speed=0.99',
	'--cache=yes',
	'--cache-pause=yes',
	'--cache-pause-wait=3',
	'--demuxer-max-bytes=1280MiB',
	'--cache-secs=6',
	'--profile=fast',
	'--hwdec=auto-safe',
	'--video-sync=audio',
	'--framedrop=decoder+vo',
	'--msg-level=ffmpeg=warn',
]

# Extra flags for progressive streams (ABC v7.1, FOX v32.1)
PROGRESSIVE_FLAGS: list[str] = [
	'--cache-pause-initial=yes',
	'--force-seekable=yes',
	'--vd-lavc-skiploopfilter=all',
]

# Extra flags for interlaced streams (CBS v2.1)
INTERLACED_FLAGS: list[str] = [
	'--cache-pause-initial=no',
	'--deinterlace=yes',
	'--vf=bwdif=mode=send_field:parity=auto:deint=interlaced',
]

# Guide numbers known to be interlaced when mediainfo is unavailable.
# CBS 2.1 is the canonical 1080i interlaced channel; add others here if found.
KNOWN_INTERLACED_GUIDE_NUMBERS: set[str] = {'2.1'}

#============================================

def _height_class(height: int) -> int:
	"""Map a pixel height to the nearest standard OTA resolution class.

	Args:
		height: The pixel height from the mediainfo Video track.

	Returns:
		1080, 720, 480, or 0 when below a recognizable threshold.
	"""
	if height >= _HEIGHT_1080:
		return 1080
	if height >= _HEIGHT_720:
		return 720
	if height >= _HEIGHT_480:
		return 480
	# height below 480 is non-standard OTA; return 0 to signal unknown
	return 0

#============================================

def probe_format(url: str, guide_number: str) -> str:
	"""Run mediainfo on a stream URL and return a short format label.

	Decision order:
	  1. Read Video.ScanType ('Interlaced' -> 'i', 'Progressive' -> 'p').
	  2. Read Video.Height to determine the resolution class (1080, 720, 480).
	  3. Combine scan suffix and height class into a label like '1080i' or '720p'.
	  4. Return an empty string on any failure (timeout, missing fields,
	     unrecognised values) so the display stays blank rather than showing
	     a guessed or stale label.

	Args:
		url: Stream URL passed to mediainfo.
		guide_number: Channel guide number, not used here but included for
		              symmetry with interlace_for_playback callers.

	Returns:
		A label such as '1080i', '720p', '1080p', or '480i'; empty string
		when the probe fails or the fields are absent or unrecognised.
	"""
	try:
		result = subprocess.run(
			['mediainfo', '--Output=JSON', url],
			capture_output=True,
			text=True,
			timeout=6,
		)
	except (FileNotFoundError, subprocess.TimeoutExpired):
		# mediainfo not installed or stream did not respond in time
		return ''
	try:
		data = json.loads(result.stdout)
	except json.JSONDecodeError:
		return ''

	# walk the tracks looking for the Video track
	tracks = data.get('media', {}).get('track', [])
	video_track: dict | None = None
	for track in tracks:
		if track.get('@type') == 'Video':
			video_track = track
			break

	if video_track is None:
		return ''

	# resolve the scan suffix from ScanType
	scan_type = video_track.get('ScanType')
	if scan_type == 'Interlaced':
		scan_suffix = 'i'
	elif scan_type == 'Progressive':
		scan_suffix = 'p'
	else:
		# ScanType absent or unrecognised; cannot build a confident label
		return ''

	# resolve the height class from Height; mediainfo may report it with spaces
	# (e.g. "1 080"), so strip spaces and accept only plain digits (no try/except)
	height_str = video_track.get('Height')
	if height_str is None:
		return ''
	height_digits = str(height_str).replace(' ', '')
	if not height_digits.isdigit():
		# non-numeric or empty height; cannot build a confident label
		return ''
	height = int(height_digits)
	res_class = _height_class(height)
	if res_class == 0:
		# unrecognised resolution; do not guess
		return ''

	# combine into a label like '1080i' or '720p'
	label = f'{res_class}{scan_suffix}'
	return label

#============================================

def interlaced_from_format(label: str) -> bool:
	"""Return True when a non-empty format label ends in 'i' (interlaced).

	This is a pure helper; it does not run any subprocess or I/O.

	Args:
		label: A format label such as '1080i', '720p', or '' (empty).

	Returns:
		True when label is non-empty and ends with 'i', False otherwise.
	"""
	return bool(label) and label.endswith('i')

#============================================

def interlace_for_playback(label: str, guide_number: str) -> bool:
	"""Derive the interlace decision for mpv playback.

	Uses the cached format label when available; falls back to the
	hard-coded KNOWN_INTERLACED_GUIDE_NUMBERS table when the label is empty
	(probe failed or channel has never been launched before).

	Args:
		label: Cached format label ('1080i', '720p', etc.) or '' when absent.
		guide_number: Channel guide number used for the fallback table lookup.

	Returns:
		True when the stream should be played with deinterlacing.
	"""
	if label:
		# confident cached label: derive from the scan suffix
		return interlaced_from_format(label)
	# no label yet (probe pending or failed): use the known-good table
	return guide_number in KNOWN_INTERLACED_GUIDE_NUMBERS

#============================================

def build_command(channel: tuner.models.Channel, interlaced: bool) -> list[str]:
	"""Build the mpv command list for a channel.

	Args:
		channel: The channel to play, supplying the stream URL.
		interlaced: True to apply the CBS interlaced profile, False for progressive.

	Returns:
		A list starting with 'mpv', followed by the stream URL, then all flags.
	"""
	# select the profile-specific flags to append after the shared set
	if interlaced:
		profile_flags = INTERLACED_FLAGS
	else:
		profile_flags = PROGRESSIVE_FLAGS
	cmd = ['mpv', channel.stream_url] + SHARED_FLAGS + profile_flags
	return cmd

#============================================

def launch(channel: tuner.models.Channel, interlaced: bool) -> str | None:
	"""Start mpv for a channel, detached, so the TUI terminal stays clean.

	mpv runs in its own process group (start_new_session=True) with all
	stdio closed so it cannot interfere with the Textual terminal.
	Non-blocking: Popen does not wait for mpv to exit; the TUI returns immediately.

	Args:
		channel: The channel to play.
		interlaced: True to use the interlaced (deinterlace) profile.

	Returns:
		None on successful spawn; an error string on failure (missing mpv or OSError).
	"""
	cmd = build_command(channel, interlaced)
	try:
		# Popen is non-blocking; mpv runs detached while the TUI continues
		subprocess.Popen(
			cmd,
			start_new_session=True,
			stdin=subprocess.DEVNULL,
			stdout=subprocess.DEVNULL,
			stderr=subprocess.DEVNULL,
		)
	except FileNotFoundError:
		return 'mpv not found - install with: brew install mpv'
	except OSError as e:
		return f'launch failed: {e}'
	return None
