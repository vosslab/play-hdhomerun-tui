"""Discover an HDHomeRun device on the LAN and resolve it into a Device.

Resolution order (first success wins):
	1. An explicit host (only when the launcher supplies one).
	2. HTTP GET http://hdhomerun.local/discover.json (primary; the device
	   answers the generic hostname today).
	3. Pure-Python UDP broadcast discovery (fallback for when the generic
	   hostname is unreachable).

The UDP packet format follows the Silicondust discover protocol confirmed
against the open-source libhdhomerun reference header hdhomerun_pkt.h: a big-endian uint16 packet
type, big-endian uint16 payload length, a tag-length-value payload, and a
trailing Ethernet-style IEEE 802.3 CRC-32 appended little-endian. The CRC is
computed with stdlib binascii.crc32 so discovery needs no extra dependency.
"""

# Standard Library
import socket
import struct
import binascii

# PIP3 modules
import requests

# local repo modules
import tuner.models

#============================================
# Protocol constants (confirmed against hdhomerun_pkt.h)
#============================================

# UDP port the device listens on for discovery requests
HDHOMERUN_DISCOVER_UDP_PORT = 65001

# Packet types
HDHOMERUN_TYPE_DISCOVER_REQ = 0x0002
HDHOMERUN_TYPE_DISCOVER_RPY = 0x0003

# TLV tag numbers
HDHOMERUN_TAG_DEVICE_TYPE = 0x01
HDHOMERUN_TAG_DEVICE_ID = 0x02
HDHOMERUN_TAG_LINEUP_URL = 0x27
HDHOMERUN_TAG_BASE_URL = 0x2A

# TLV values for the request
HDHOMERUN_DEVICE_TYPE_TUNER = 0x00000001
HDHOMERUN_DEVICE_ID_WILDCARD = 0xFFFFFFFF

# Generic hostname the device answers on the LAN today
HDHOMERUN_DEFAULT_HOSTNAME = 'hdhomerun.local'

# Broadcast address for the UDP fallback
UDP_BROADCAST_ADDRESS = '255.255.255.255'

# Short fixed HTTP timeout in seconds
HTTP_TIMEOUT_SECONDS = 3.0

# UDP receive timeout per attempt and number of broadcast attempts
UDP_TIMEOUT_SECONDS = 0.2
UDP_ATTEMPTS = 2

# maximum reply size we are willing to read from the socket
HDHOMERUN_MAX_PACKET_SIZE = 1460

#============================================
# Pure CRC + TLV helpers (no network)
#============================================

def _ethernet_crc32(data: bytes) -> int:
	"""Compute the Ethernet-style IEEE 802.3 CRC-32 over data.

	binascii.crc32 implements the same reflected CRC-32 (init 0xFFFFFFFF,
	polynomial 0xEDB88320, final XOR 0xFFFFFFFF) used by the device, so it
	matches hdhomerun_pkt_calc_crc byte for byte.

	Args:
		data: The bytes to checksum (packet type + length + payload).

	Returns:
		The 32-bit CRC as an unsigned int.
	"""
	# mask to 32 bits so the value is always an unsigned int
	crc = binascii.crc32(data) & 0xFFFFFFFF
	return crc


#============================================

def _encode_tlv(tag: int, value: bytes) -> bytes:
	"""Encode one tag-length-value triple.

	Only single-byte lengths are produced because request values are short
	(<= 127 bytes). Longer values are not needed for discovery requests.

	Args:
		tag: The 8-bit TLV tag number.
		value: The raw value bytes.

	Returns:
		The encoded TLV bytes.
	"""
	# single-byte length is valid for values up to 127 bytes
	length = len(value)
	tlv = struct.pack('>BB', tag, length) + value
	return tlv


#============================================

def build_discovery_request() -> bytes:
	"""Build the UDP discovery request packet bytes.

	Packet shape: big-endian uint16 type, big-endian uint16 payload length,
	the TLV payload (device-type tuner, device-id wildcard), then the
	trailing CRC-32 appended little-endian.

	Returns:
		The complete request packet ready to broadcast.
	"""
	# device-type tag carries the 4-byte tuner type, big-endian
	device_type_value = struct.pack('>I', HDHOMERUN_DEVICE_TYPE_TUNER)
	device_type_tlv = _encode_tlv(HDHOMERUN_TAG_DEVICE_TYPE, device_type_value)
	# device-id tag carries the 4-byte wildcard id, big-endian
	device_id_value = struct.pack('>I', HDHOMERUN_DEVICE_ID_WILDCARD)
	device_id_tlv = _encode_tlv(HDHOMERUN_TAG_DEVICE_ID, device_id_value)
	# assemble the payload from the two request tags
	payload = device_type_tlv + device_id_tlv
	# header is type then payload length, both big-endian uint16
	header = struct.pack('>HH', HDHOMERUN_TYPE_DISCOVER_REQ, len(payload))
	# CRC covers the header and payload (everything before the CRC field)
	body = header + payload
	crc = _ethernet_crc32(body)
	# CRC is appended little-endian per the protocol
	packet = body + struct.pack('<I', crc)
	return packet


#============================================

def _read_var_length(data: bytes, offset: int) -> tuple[int, int]:
	"""Read a TLV length field that may be one or two bytes.

	A length <= 127 uses a single byte (high bit clear). A length >= 128
	uses two bytes: the first holds the low 7 bits with the high bit set,
	the second holds the length shifted down 7 bits.

	Args:
		data: The reply buffer.
		offset: Index of the first length byte.

	Returns:
		A (length, next_offset) tuple.
	"""
	first = data[offset]
	# high bit clear means a single-byte length
	if first & 0x80 == 0:
		return (first, offset + 1)
	# two-byte length: low 7 bits from first byte, rest from second byte
	length = (first & 0x7F) | (data[offset + 1] << 7)
	return (length, offset + 2)


#============================================

def parse_discovery_reply(data: bytes) -> tuner.models.Device:
	"""Parse a UDP discovery reply packet into a Device.

	Validates the packet type (0x0003) and the trailing little-endian CRC,
	then walks the TLV payload pulling the base URL (0x2A) and lineup URL
	(0x27). Unknown tags are skipped, not treated as errors.

	Args:
		data: The raw reply packet bytes.

	Returns:
		A populated tuner.models.Device.

	Raises:
		ValueError: When the packet is too short, has the wrong type, fails
			the CRC check, or is missing the base/lineup URL tags.
	"""
	# packet must hold at least a 4-byte header and a 4-byte CRC
	if len(data) < 8:
		raise ValueError(f"discovery reply too short: {len(data)} bytes")
	packet_type, payload_length = struct.unpack('>HH', data[0:4])
	if packet_type != HDHOMERUN_TYPE_DISCOVER_RPY:
		raise ValueError(f"unexpected packet type 0x{packet_type:04x}")
	# payload sits between the 4-byte header and the trailing 4-byte CRC
	payload_end = 4 + payload_length
	# verify the framed length fits within the buffer plus the CRC field
	if payload_end + 4 > len(data):
		raise ValueError("discovery reply payload length exceeds buffer")
	# CRC covers the header and payload; it is stored little-endian
	body = data[0:payload_end]
	expected_crc = _ethernet_crc32(body)
	(actual_crc,) = struct.unpack('<I', data[payload_end:payload_end + 4])
	if actual_crc != expected_crc:
		raise ValueError("discovery reply CRC mismatch")
	# walk the TLV payload collecting the tags we care about
	tags = _parse_tlv_payload(data[4:payload_end])
	if HDHOMERUN_TAG_BASE_URL not in tags:
		raise ValueError("discovery reply missing base URL tag")
	if HDHOMERUN_TAG_LINEUP_URL not in tags:
		raise ValueError("discovery reply missing lineup URL tag")
	base_url = tags[HDHOMERUN_TAG_BASE_URL].decode('utf-8')
	lineup_url = tags[HDHOMERUN_TAG_LINEUP_URL].decode('utf-8')
	# device id is optional in the reply; default to wildcard text when absent
	device_id = _decode_device_id(tags)
	# derive a best-effort ip from the base url host portion
	ip = _host_from_url(base_url)
	device = tuner.models.Device(
		friendly_name='HDHomeRun',
		base_url=base_url,
		lineup_url=lineup_url,
		device_id=device_id,
		ip=ip,
	)
	return device


#============================================

def _parse_tlv_payload(payload: bytes) -> dict[int, bytes]:
	"""Walk a TLV payload into a tag-to-value mapping.

	Unknown tags are kept in the mapping; callers pick the tags they need.

	Args:
		payload: The payload bytes (between header and CRC).

	Returns:
		A dict mapping each tag number to its raw value bytes.
	"""
	tags: dict[int, bytes] = {}
	offset = 0
	# step through tag, length, value triples until the payload is consumed
	while offset < len(payload):
		tag = payload[offset]
		offset += 1
		length, offset = _read_var_length(payload, offset)
		value = payload[offset:offset + length]
		offset += length
		tags[tag] = value
	return tags


#============================================

def _decode_device_id(tags: dict[int, bytes]) -> str:
	"""Pull the device id from parsed reply tags, if present.

	Args:
		tags: The tag-to-value mapping from the reply payload.

	Returns:
		An uppercase hex device id string, or 'FFFFFFFF' when absent.
	"""
	# device id tag is optional in the reply per the protocol
	if HDHOMERUN_TAG_DEVICE_ID not in tags:
		return 'FFFFFFFF'
	(device_id_int,) = struct.unpack('>I', tags[HDHOMERUN_TAG_DEVICE_ID])
	device_id = f"{device_id_int:08X}"
	return device_id


#============================================

def _host_from_url(url: str) -> str:
	"""Extract the host (or ip) portion of an http base URL.

	Args:
		url: A URL like "http://192.168.1.5:80".

	Returns:
		The host portion, or an empty string when it cannot be parsed.
	"""
	# strip the scheme and any path/port to leave the bare host
	without_scheme = url.split('://', 1)[-1]
	host = without_scheme.split('/', 1)[0]
	host = host.split(':', 1)[0]
	return host


#============================================
# HTTP discovery
#============================================

def device_from_discover_json(payload: dict, fallback_base_url: str) -> tuner.models.Device:
	"""Build a Device from a parsed discover.json dict.

	Args:
		payload: The parsed discover.json mapping from the device.
		fallback_base_url: Base URL to use when the JSON omits BaseURL
			(for example when fetched via an explicit host).

	Returns:
		A populated tuner.models.Device.

	Raises:
		ValueError: When the JSON lacks a usable lineup URL.
	"""
	# BaseURL is present on real devices; fall back to the fetched host url
	base_url = payload.get('BaseURL', fallback_base_url)
	# LineupURL is required to enumerate channels later
	if 'LineupURL' in payload:
		lineup_url = payload['LineupURL']
	else:
		# older firmware exposes the lineup under a fixed path off the base
		lineup_url = base_url.rstrip('/') + '/lineup.json'
	friendly_name = payload.get('FriendlyName', 'HDHomeRun')
	device_id = payload.get('DeviceID', '')
	# LocalIP is the device-reported ip; fall back to the base url host
	ip = payload.get('LocalIP', _host_from_url(base_url))
	device = tuner.models.Device(
		friendly_name=friendly_name,
		base_url=base_url,
		lineup_url=lineup_url,
		device_id=device_id,
		ip=ip,
	)
	return device


#============================================

def _discover_http(base_url: str) -> tuner.models.Device:
	"""Fetch and parse discover.json from a base URL into a Device.

	Args:
		base_url: The device base URL, e.g. "http://hdhomerun.local".

	Returns:
		A populated tuner.models.Device.

	Raises:
		requests.RequestException: On network/HTTP failure.
		ValueError: When the response is not valid discovery JSON.
	"""
	discover_url = base_url.rstrip('/') + '/discover.json'
	# single user-initiated LAN request (not a chained/looped fetch), so no throttle sleep
	response = requests.get(discover_url, timeout=HTTP_TIMEOUT_SECONDS)
	response.raise_for_status()
	payload = response.json()
	device = device_from_discover_json(payload, base_url)
	return device


#============================================
# UDP discovery
#============================================

def _discover_udp() -> tuner.models.Device:
	"""Broadcast a UDP discovery request and parse the first reply.

	Sends the request to 255.255.255.255:65001 with a short receive timeout,
	retrying a small fixed number of times.

	Returns:
		A populated tuner.models.Device from the first valid reply.

	Raises:
		OSError: When no reply arrives within the attempts (socket timeout).
		ValueError: When a reply arrives but cannot be parsed.
	"""
	request = build_discovery_request()
	# UDP datagram socket configured for broadcast with a short timeout
	udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
	udp_socket.settimeout(UDP_TIMEOUT_SECONDS)
	target = (UDP_BROADCAST_ADDRESS, HDHOMERUN_DISCOVER_UDP_PORT)
	last_error: OSError | None = None
	# retry the broadcast a few times before giving up
	for _attempt in range(UDP_ATTEMPTS):
		udp_socket.sendto(request, target)
		# narrow try: only the blocking recv can raise a timeout here
		try:
			data, _addr = udp_socket.recvfrom(HDHOMERUN_MAX_PACKET_SIZE)
		except socket.timeout as timeout_error:
			last_error = timeout_error
			continue
		udp_socket.close()
		device = parse_discovery_reply(data)
		return device
	udp_socket.close()
	# no reply across all attempts; surface the last timeout
	raise OSError("UDP discovery received no reply") from last_error


#============================================
# Public entry point
#============================================

def discover_devices(host: str | None = None) -> tuner.models.Device:
	"""Resolve an HDHomeRun device into a Device, first success wins.

	Order: an explicit host (when supplied), then HTTP discover.json on the
	generic hostname, then UDP broadcast as the fallback.

	Args:
		host: Optional explicit host (ip or hostname) from the launcher.
			When given, http://<host>/discover.json is tried first.

	Returns:
		The resolved tuner.models.Device.

	Raises:
		RuntimeError: When every method fails. The message lists each
			method and hostname that was attempted.
	"""
	# record each attempt so a total failure reports what was tried
	attempts: list[str] = []
	# 1. explicit host from the launcher takes priority when provided
	if host is not None:
		host_base_url = f"http://{host}"
		attempts.append(f"HTTP {host_base_url}/discover.json")
		# narrow try: only the network call can fail here
		try:
			return _discover_http(host_base_url)
		except (requests.RequestException, ValueError):
			pass
	# 2. HTTP discovery on the generic hostname (primary path)
	default_base_url = f"http://{HDHOMERUN_DEFAULT_HOSTNAME}"
	attempts.append(f"HTTP {default_base_url}/discover.json")
	# narrow try: only the network call can fail here
	try:
		return _discover_http(default_base_url)
	except (requests.RequestException, ValueError):
		pass
	# 3. UDP broadcast fallback
	attempts.append(f"UDP broadcast {UDP_BROADCAST_ADDRESS}:{HDHOMERUN_DISCOVER_UDP_PORT}")
	# narrow try: socket timeout or parse failure means the fallback failed
	try:
		return _discover_udp()
	except (OSError, ValueError):
		pass
	# every method failed; report the full list of attempts
	attempted = '; '.join(attempts)
	raise RuntimeError(f"HDHomeRun discovery failed. Attempted: {attempted}")
