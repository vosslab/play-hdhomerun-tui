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

# Guide numbers known to be interlaced when the ffprobe probe fails.
# CBS 2.1 is the canonical 1080i interlaced channel; add others here if found.
KNOWN_INTERLACED_GUIDE_NUMBERS: set[str] = {'2.1'}

#============================================

def _height_class(height: int) -> int:
	"""Map a pixel height to the nearest standard OTA resolution class.

	Args:
		height: The pixel height from the ffprobe video stream.

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

# ffprobe field_order values that mean the stream is interlaced.
# 'progressive' maps to 'p'; anything in this set maps to 'i'.
_INTERLACED_FIELD_ORDERS: set[str] = {'tt', 'bb', 'tb', 'bt'}

def probe_format(url: str, guide_number: str) -> str:
	"""Run ffprobe on a stream URL and return a short format label.

	ffprobe reads the first video stream's height and field order from a
	bounded sample of the stream.  mediainfo is unusable here because it
	never reaches end-of-file on a continuous HDHomeRun transport stream and
	hangs until killed, so every probe timed out and the label stayed blank.

	Decision order:
	  1. Read stream.field_order ('progressive' -> 'p', 'tt'/'bb'/'tb'/'bt'
	     -> 'i').
	  2. Read stream.height to determine the resolution class (1080, 720, 480).
	  3. Combine scan suffix and height class into a label like '1080i' or '720p'.
	  4. Return an empty string on any failure (timeout, missing fields,
	     unrecognised values) so the display stays blank rather than showing
	     a guessed or stale label.

	Args:
		url: Stream URL passed to ffprobe.
		guide_number: Channel guide number, not used here but included for
		              symmetry with interlace_for_playback callers.

	Returns:
		A label such as '1080i', '720p', '1080p', or '480i'; empty string
		when the probe fails or the fields are absent or unrecognised.
	"""
	# -read_intervals '%+#1' stops after the first packet so the bounded probe
	# returns in seconds on a continuous stream instead of reading forever
	cmd = [
		'ffprobe',
		'-hide_banner',
		'-loglevel', 'error',
		'-select_streams', 'v:0',
		'-show_entries', 'stream=height,field_order',
		'-of', 'json',
		'-read_intervals', '%+#1',
		url,
	]
	try:
		result = subprocess.run(
			cmd,
			capture_output=True,
			text=True,
			timeout=12,
		)
	except (FileNotFoundError, subprocess.TimeoutExpired):
		# ffprobe not installed or stream did not respond in time
		return ''
	try:
		data = json.loads(result.stdout)
	except json.JSONDecodeError:
		return ''

	# first video stream only; -select_streams v:0 yields at most one entry
	streams = data.get('streams', [])
	if not streams:
		return ''
	video_stream = streams[0]

	# resolve the scan suffix from field_order
	field_order = video_stream.get('field_order')
	if field_order == 'progressive':
		scan_suffix = 'p'
	elif field_order in _INTERLACED_FIELD_ORDERS:
		scan_suffix = 'i'
	else:
		# field_order absent or 'unknown'; cannot build a confident label
		return ''

	# resolve the height class; ffprobe reports height as a plain JSON integer
	height_value = video_stream.get('height')
	if not isinstance(height_value, int):
		return ''
	res_class = _height_class(height_value)
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
