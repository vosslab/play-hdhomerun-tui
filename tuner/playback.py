"""Launch mpv for an HDHomeRun OTA channel, with deinterlace auto-detection."""

# Standard Library
import json
import subprocess

# local repo modules
import tuner.models

#============================================
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

def is_interlaced(url: str, guide_number: str) -> bool:
	"""Determine whether a stream is interlaced.

	Decision order:
	  1. Run mediainfo on the URL and read Video.ScanType:
	     'Interlaced' -> True, 'Progressive' -> False.
	  2. If ScanType absent, use Video.Height:
	     1080-class -> True (interlaced), 720-class -> False (progressive).
	  3. If mediainfo times out, fails, or lacks both fields, fall back to
	     the known-good constant KNOWN_INTERLACED_GUIDE_NUMBERS.

	Args:
		url: The stream URL to probe with mediainfo.
		guide_number: The channel guide number, used as the final fallback key.

	Returns:
		True when the stream is interlaced, False when progressive.
	"""
	try:
		result = subprocess.run(
			['mediainfo', '--Output=JSON', url],
			capture_output=True,
			text=True,
			timeout=6,
		)
	except FileNotFoundError:
		return guide_number in KNOWN_INTERLACED_GUIDE_NUMBERS
	except subprocess.TimeoutExpired:
		return guide_number in KNOWN_INTERLACED_GUIDE_NUMBERS
	try:
		data = json.loads(result.stdout)
	except json.JSONDecodeError:
		return guide_number in KNOWN_INTERLACED_GUIDE_NUMBERS

	# walk the tracks looking for the Video track
	tracks = data.get('media', {}).get('track', [])
	video_track: dict | None = None
	for track in tracks:
		if track.get('@type') == 'Video':
			video_track = track
			break

	if video_track is None:
		# no video track found; fall back to the known-good table
		return guide_number in KNOWN_INTERLACED_GUIDE_NUMBERS

	# primary: ScanType field
	scan_type = video_track.get('ScanType')
	if scan_type == 'Interlaced':
		return True
	if scan_type == 'Progressive':
		return False

	# secondary: Height field (1080-class is interlaced OTA, 720-class is progressive)
	height_str = video_track.get('Height')
	if height_str is not None:
		try:
			height = int(str(height_str).replace(' ', ''))
		except ValueError:
			height = 0
		if height >= 1000:
			# 1080i class
			return True
		if height >= 700:
			# 720p class
			return False

	# final fallback: known-good table
	return guide_number in KNOWN_INTERLACED_GUIDE_NUMBERS

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
