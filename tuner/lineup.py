"""Fetch and parse the HDHomeRun channel lineup from a device."""

# PIP3 modules
import requests

# local repo modules
import tuner.models

#============================================

def parse_channels(entries: list) -> list[tuner.models.Channel]:
	"""Parse a list of raw lineup JSON entries into Channel objects.

	Separates parsing from network access so tests can use a fixture
	without making a real HTTP request.

	Required keys (always present, accessed directly to fail loudly on bad data):
	  GuideNumber, GuideName, URL

	Intentionally optional keys (absent when the value is 0 or unknown):
	  HD, Favorite, SignalQuality, SignalStrength

	Args:
		entries: List of dicts as returned by the device /lineup.json endpoint.

	Returns:
		List of Channel dataclass instances, one per entry.
	"""
	channels = []
	for entry in entries:
		# required keys -- direct access so missing data raises KeyError immediately
		guide_number = entry["GuideNumber"]
		guide_name = entry["GuideName"]
		stream_url = entry["URL"]

		# HD and Favorite are absent when the value would be 0 (intentional optional default)
		hd = bool(entry.get("HD", 0))
		device_favorite = bool(entry.get("Favorite", 0))

		# SignalQuality and SignalStrength are absent for some channels; preserve None
		signal_quality = entry.get("SignalQuality")
		signal_strength = entry.get("SignalStrength")

		channel = tuner.models.Channel(
			guide_number=guide_number,
			guide_name=guide_name,
			stream_url=stream_url,
			hd=hd,
			device_favorite=device_favorite,
			signal_quality=signal_quality,
			signal_strength=signal_strength,
		)
		channels.append(channel)
	return channels

#============================================

def fetch_channels(device: tuner.models.Device) -> list[tuner.models.Channel]:
	"""Fetch and parse the lineup from the given device over HTTP.

	Sends a GET request to <device.base_url>/lineup.json, parses the
	JSON body, and delegates to parse_channels for object construction.

	Args:
		device: A Device instance with a valid base_url.

	Returns:
		List of Channel dataclass instances from the device lineup.
	"""
	# short fixed timeout: connect 5 s, read 10 s
	# single user-initiated LAN request (not a chained/looped fetch), so no throttle sleep
	response = requests.get(device.base_url + "/lineup.json", timeout=(5, 10))
	response.raise_for_status()
	entries = response.json()
	return parse_channels(entries)
