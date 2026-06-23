"""Shared data models for HDHomeRun device and channel information."""

# Standard Library
import dataclasses

#============================================

@dataclasses.dataclass
class Device:
	"""Represents a discovered HDHomeRun device on the LAN."""
	# Human-readable name from the device (e.g. "HDHomeRun FLEX DUO")
	friendly_name: str
	# Base URL for the device, e.g. "http://hdhomerun.local"
	base_url: str
	# Full URL to the lineup JSON endpoint
	lineup_url: str
	# Device identifier string from discover.json
	device_id: str
	# IP address of the device
	ip: str

#============================================

@dataclasses.dataclass
class Channel:
	"""Represents a single OTA channel entry from the HDHomeRun lineup."""
	# Guide number string as returned by the device, e.g. "2.1" or "11.1"
	guide_number: str
	# Human-readable channel name, e.g. "CBS2-HD"
	guide_name: str
	# Full HTTP stream URL for this channel
	stream_url: str
	# True when the lineup HD field is 1
	hd: bool
	# True when the lineup Favorite field is 1 (device-set favorite)
	device_favorite: bool
	# Signal quality percentage (0-100) from the lineup, or None when absent
	signal_quality: int | None
	# Signal strength percentage (0-100) from the lineup, or None when absent
	signal_strength: int | None

	@property
	def sort_key(self) -> tuple[int, int]:
		"""Numeric sort key parsed from guide_number.

		Splits on '.' and converts major/minor to ints so that
		"7.1" sorts before "11.1" (numeric, not lexicographic).

		Returns:
			A (major, minor) tuple of ints.
		"""
		parts = self.guide_number.split('.')
		major = int(parts[0])
		# default minor to 0 when the guide number has no sub-channel
		minor = int(parts[1]) if len(parts) > 1 else 0
		return (major, minor)
