"""Textual TUI that discovers an HDHomeRun, lists channels, and launches mpv.

This module ties the data, state, and playback modules into a modeless,
zero-config channel picker.  The standard path is: run, auto-discover,
auto-fetch the lineup, sort into Favorites / Frequent / All channels blocks,
arrow + Enter to launch mpv detached, and stay live.

Two pure module-level helpers (format_reception and format_guide_number) hold
the row-rendering logic so it is unit-testable without instantiating the app.
"""

# Standard Library
import textwrap

# PIP3 modules
import textual
import textual.app
import textual.binding
import textual.widgets

# local repo modules
import tuner.state
import tuner.lineup
import tuner.models
import tuner.discover
import tuner.playback

#============================================
# Reception color thresholds (quality-based), per the user-facing contract.
# green for >= 80, yellow for 60-79, red for < 60.
_RECEPTION_GREEN_MIN = 80
_RECEPTION_YELLOW_MIN = 60

# Persistent footer text listing the main key bindings.
_FOOTER_TEXT = "Enter/p play | f favorite | r refresh | q quit"

#============================================

def format_reception(signal_quality: int | None, signal_strength: int | None) -> str:
	"""Build the compact reception field 'Q<quality>/S<strength>'.

	Quality is shown first because it predicts playback stability better than
	strength.  A missing value is omitted (no placeholder); when both values are
	absent the field is an empty string.  This is the raw-text logic only, so it
	is assertable without the TUI; color is applied separately as markup.

	Args:
		signal_quality: SignalQuality int from the lineup, or None when absent.
		signal_strength: SignalStrength int from the lineup, or None when absent.

	Returns:
		A string like 'Q80/S63', 'Q80', 'S63', or '' when both are None.
	"""
	parts: list[str] = []
	# quality first, since it better predicts playback stability
	if signal_quality is not None:
		parts.append(f"Q{signal_quality}")
	if signal_strength is not None:
		parts.append(f"S{signal_strength}")
	# join with a slash so 'Q80/S63'; a single present value has no slash
	reception_text = "/".join(parts)
	return reception_text

#============================================

def reception_color(signal_quality: int | None) -> str:
	"""Pick a subtle color name for the reception field based on quality.

	Args:
		signal_quality: SignalQuality int from the lineup, or None when absent.

	Returns:
		A Textual/Rich color name: 'green' (>= 80), 'yellow' (60-79),
		'red' (< 60), or 'dim' when quality is unknown.
	"""
	# unknown quality gets a muted style rather than a traffic-light color
	if signal_quality is None:
		return "dim"
	if signal_quality >= _RECEPTION_GREEN_MIN:
		return "green"
	if signal_quality >= _RECEPTION_YELLOW_MIN:
		return "yellow"
	return "red"

#============================================

def format_guide_number(guide_number: str, major_width: int) -> str:
	"""Dot-justify a guide number so decimal points align in a column.

	The major part is right-aligned to major_width and the minor part is
	left-aligned, so ' 7.1', '11.1', '24.2', and '24.10' line up on the dot.

	Args:
		guide_number: Guide number string, e.g. '2.1' or '24.10'.
		major_width: Width to right-align the major part to, derived from the
			widest major part among the visible channels.

	Returns:
		The dot-justified guide-number string.
	"""
	parts = guide_number.split(".")
	major = parts[0]
	# default the minor part to empty when a guide number has no sub-channel
	minor = parts[1] if len(parts) > 1 else ""
	# right-align the major part, left-align the minor part (minor padded to 2)
	justified = f"{major.rjust(major_width)}.{minor.ljust(2)}"
	return justified

#============================================

def major_width_for_channels(channels: list[tuner.models.Channel]) -> int:
	"""Compute the major-part width to right-align guide numbers to.

	Args:
		channels: The visible channels whose guide numbers drive the column width.

	Returns:
		The character width of the widest major part, at least 1.
	"""
	width = 1
	for channel in channels:
		major = channel.guide_number.split(".")[0]
		if len(major) > width:
			width = len(major)
	return width

#============================================

def _escape_markup(text: str) -> str:
	"""Escape square brackets so guide names cannot break Textual markup.

	Args:
		text: Raw text that may contain '[' or ']'.

	Returns:
		The text with markup-significant brackets escaped.
	"""
	# doubling the opening bracket is Textual's escape for literal '['
	escaped = text.replace("[", "[[")
	return escaped

#============================================

def render_channel_row(
	channel: tuner.models.Channel,
	major_width: int,
	is_favorite: bool,
	play_count: int,
) -> str:
	"""Build the Textual-markup label text for one channel row.

	Layout: star marker, dot-justified guide number, guide name, HD tag, an
	optional play-count indicator for frequent rows, and the color-coded
	reception field.

	Args:
		channel: The channel to render.
		major_width: Major-part width for dot-justification.
		is_favorite: True to show the favorite star marker.
		play_count: Play count; a positive value adds a small indicator.

	Returns:
		A single line of Textual markup for a ListItem label.
	"""
	# star marker column: a filled star for favorites, a space otherwise
	star = "*" if is_favorite else " "
	number_text = format_guide_number(channel.guide_number, major_width)
	name_text = _escape_markup(channel.guide_name)
	# HD tag only when the channel reports HD
	hd_text = " HD" if channel.hd else ""
	# play-count indicator only for channels with history
	count_text = f"  ({play_count}x)" if play_count > 0 else ""

	reception_text = format_reception(channel.signal_quality, channel.signal_strength)
	if reception_text:
		color = reception_color(channel.signal_quality)
		reception_markup = f"  [{color}]{reception_text}[/{color}]"
	else:
		reception_markup = ""

	# assemble the row, then return the variable (no work in the return statement)
	row = f"{star} {number_text}  {name_text}{hd_text}{count_text}{reception_markup}"
	return row

#============================================

class HDHRApp(textual.app.App):
	"""Textual app for the HDHomeRun OTA channel launcher.

	The app moves through a small explicit set of screen states (discovering,
	loading-lineup, ready, launching, launched, launch-error, error) surfaced in
	a status line above the channel list.  There is exactly one interactive mode:
	the channel list.  The same keys always mean the same thing and q always
	quits, so the user never gets stuck.
	"""

	# CSS keeps the status line and footer visually distinct from the list.
	CSS = textwrap.dedent(
		"""
		#status {
			height: auto;
			padding: 0 1;
			color: $text;
		}
		#channel_list {
			height: 1fr;
		}
		#footer {
			height: 1;
			padding: 0 1;
			background: $panel;
			color: $text-muted;
		}
		"""
	)

	# Key bindings settled in the user-facing contract.  Up/Down are handled by
	# the ListView itself; p/Enter/f/r/q are bound here.  Enter is delivered as
	# a ListView.Selected message and handled in on_list_view_selected.
	BINDINGS = [
		textual.binding.Binding("p", "play", "play"),
		textual.binding.Binding("f", "favorite", "favorite"),
		textual.binding.Binding("r", "refresh", "refresh"),
		textual.binding.Binding("q", "quit", "quit"),
	]

	def __init__(self, host: str | None = None) -> None:
		"""Initialize the app.

		Args:
			host: Optional bare hostname or IP for the --host escape hatch.  When
				given it is tried before HTTP and UDP discovery.
		"""
		super().__init__()
		# the --host escape hatch value, passed straight to discover_devices
		self._host = host
		# populated after discovery / lineup fetch
		self._device: tuner.models.Device | None = None
		self._state: tuner.state.State | None = None
		# the ordered list of currently visible channels, parallel to ListView rows
		self._visible_channels: list[tuner.models.Channel] = []
		# computed major width for dot-justification of the visible set
		self._major_width = 1

	#============================================

	def compose(self) -> textual.app.ComposeResult:
		"""Build the widget tree: status line, channel list, persistent footer.

		Returns:
			The Textual compose result yielding the app's widgets.
		"""
		# status line communicates the current screen state to the user
		yield textual.widgets.Static("Looking for HDHomeRun...", id="status")
		# the single channel list; Up/Down move the highlight natively
		yield textual.widgets.ListView(id="channel_list")
		# persistent footer of the main key bindings
		yield textual.widgets.Static(_FOOTER_TEXT, id="footer")

	#============================================

	def on_mount(self) -> None:
		"""Kick off discovery and lineup loading once the UI is mounted."""
		# run discovery + lineup off the event loop so the UI stays responsive
		self._load_device_and_lineup()

	#============================================

	def _set_status(self, message: str) -> None:
		"""Update the status line text.

		Args:
			message: The text to show in the status line.
		"""
		status = self.query_one("#status", textual.widgets.Static)
		status.update(message)

	#============================================

	@textual.work(thread=True, exclusive=True)
	def _load_device_and_lineup(self) -> None:
		"""Discover the device and fetch the lineup in a worker thread.

		Runs in a thread so the ~seconds of network work never blocks the Textual
		event loop.  UI updates are marshalled back via call_from_thread.
		"""
		host_hint = self._host if self._host else "hdhomerun.local"
		self.call_from_thread(
			self._set_status, f"Looking for HDHomeRun ({host_hint})..."
		)
		# discovery may raise RuntimeError listing every method/hostname tried
		try:
			device = tuner.discover.discover_devices(self._host)
		except RuntimeError as discovery_error:
			# concise error state with the --host recovery hint, never a traceback
			message = (
				f"Discovery failed: {discovery_error}\n"
				f"Try: hdhr_tui.py --host <hostname-or-ip>"
			)
			self.call_from_thread(self._set_status, message)
			return

		self.call_from_thread(
			self._set_status, f"Loading channels from {device.base_url}..."
		)
		channels = tuner.lineup.fetch_channels(device)

		# build / load state, seed favorites on first run, prune to current lineup
		state = tuner.state.State()
		state.seed_favorites_from_channels(channels)
		state.prune_to_lineup(channels)

		# hand results back to the main thread to populate the list
		self.call_from_thread(self._on_lineup_ready, device, state, channels)

	#============================================

	def _on_lineup_ready(
		self,
		device: tuner.models.Device,
		state: tuner.state.State,
		channels: list[tuner.models.Channel],
	) -> None:
		"""Store discovered data and render the channel list (main thread).

		Args:
			device: The resolved device.
			state: The loaded, seeded, pruned state store.
			channels: The fetched channel lineup.
		"""
		self._device = device
		self._state = state
		self._render_blocks(channels)
		self._set_status(f"Ready - {device.friendly_name} ({len(channels)} channels)")

	#============================================

	def _render_blocks(self, channels: list[tuner.models.Channel]) -> None:
		"""Sort channels into blocks and (re)populate the ListView.

		Empty blocks are hidden (no header is shown for them).  The highlight is
		left at the top after a full render; callers that need to preserve the
		highlight handle that separately.

		Args:
			channels: The full channel lineup to sort and display.
		"""
		# state is always present once the lineup is ready
		state = self._state
		favorites, frequent, all_channels = state.sort_blocks(channels)

		# the visible set is the concatenation of the three blocks, in order
		visible: list[tuner.models.Channel] = []
		visible.extend(favorites)
		visible.extend(frequent)
		visible.extend(all_channels)
		self._visible_channels = visible
		self._major_width = major_width_for_channels(visible)

		list_view = self.query_one("#channel_list", textual.widgets.ListView)
		list_view.clear()

		# append a non-selectable header row for each non-empty block, then its rows
		self._append_block(list_view, "Favorites", favorites)
		self._append_block(list_view, "Frequent", frequent)
		self._append_block(list_view, "All channels", all_channels)

	#============================================

	def _append_block(
		self,
		list_view: textual.widgets.ListView,
		title: str,
		channels: list[tuner.models.Channel],
	) -> None:
		"""Append a block header and its channel rows to the list view.

		Empty blocks are skipped entirely so first run shows only All channels.

		Args:
			list_view: The ListView to append to.
			title: The block header text.
			channels: The channels in this block (already sorted).
		"""
		# hide empty blocks: no header, no rows
		if not channels:
			return
		# header row is disabled so it cannot be highlighted or selected
		header_label = textual.widgets.Label(f"[b]{title}[/b]")
		header_item = textual.widgets.ListItem(header_label, disabled=True)
		header_item.add_class("block-header")
		list_view.append(header_item)

		state = self._state
		play_counts = state.play_counts
		favorites = state.favorites
		for channel in channels:
			is_favorite = channel.guide_number in favorites
			# default count to 0 for channels with no recorded history
			play_count = play_counts.get(channel.guide_number, 0)
			row_text = render_channel_row(
				channel, self._major_width, is_favorite, play_count
			)
			row_label = textual.widgets.Label(row_text)
			# id encodes the guide number so selection maps back to a channel;
			# dots are not valid in ids, so encode them as underscores
			row_id = "ch_" + channel.guide_number.replace(".", "_")
			row_item = textual.widgets.ListItem(row_label, id=row_id)
			list_view.append(row_item)

	#============================================

	def _highlighted_channel(self) -> tuner.models.Channel | None:
		"""Return the channel under the current highlight, or None.

		Header rows are disabled and not selectable, so a highlighted item always
		maps to a channel via its id.

		Returns:
			The highlighted Channel, or None when nothing is highlighted.
		"""
		list_view = self.query_one("#channel_list", textual.widgets.ListView)
		item = list_view.highlighted_child
		if item is None or item.id is None:
			return None
		# decode the guide number from the row id (ch_24_10 -> 24.10)
		if not item.id.startswith("ch_"):
			return None
		guide_number = item.id[len("ch_"):].replace("_", ".")
		for channel in self._visible_channels:
			if channel.guide_number == guide_number:
				return channel
		return None

	#============================================

	def _select_channel_by_guide_number(self, guide_number: str) -> None:
		"""Move the highlight to the row matching a guide number, if present.

		Used after a favorite toggle re-sorts the blocks so the highlight stays
		on the same channel.

		Args:
			guide_number: The guide number to re-highlight.
		"""
		list_view = self.query_one("#channel_list", textual.widgets.ListView)
		target_id = "ch_" + guide_number.replace(".", "_")
		for index, item in enumerate(list_view.children):
			if item.id == target_id:
				list_view.index = index
				return

	#============================================

	def on_list_view_selected(
		self, event: textual.widgets.ListView.Selected
	) -> None:
		"""Handle Enter on a channel row by launching it.

		Args:
			event: The ListView.Selected message carrying the chosen item.
		"""
		# Enter and click both produce Selected; route to the shared play path
		self.action_play()

	#============================================

	def action_play(self) -> None:
		"""Play the highlighted channel: record, probe interlace, launch detached."""
		channel = self._highlighted_channel()
		# nothing to do on status screens or empty selection
		if channel is None:
			return
		state = self._state
		# record the selection immediately so frequent ordering reflects intent
		state.record_selection(channel.guide_number)
		self._set_status(
			f"Starting {channel.guide_number} {channel.guide_name} "
			f"(checking stream format...)"
		)
		# probe + launch in a worker thread so the ~6s mediainfo probe and the
		# detached spawn never block the event loop (hard criterion)
		self._probe_and_launch(channel)

	#============================================

	@textual.work(thread=True)
	def _probe_and_launch(self, channel: tuner.models.Channel) -> None:
		"""Detect interlace (cached), then launch mpv detached, in a thread.

		Args:
			channel: The channel to probe and launch.
		"""
		# use the cached verdict when present so repeat launches skip the ~6s probe
		verdict = self._state.interlace_verdict(channel.guide_number)
		if verdict is None:
			# first time for this channel: probe off the event loop, then cache it
			verdict = tuner.playback.is_interlaced(
				channel.stream_url, channel.guide_number
			)
			self._state.set_interlace(channel.guide_number, verdict)
		# launch detached; a non-None return is a concise launch-time error
		launch_error = tuner.playback.launch(channel, verdict)
		self.call_from_thread(self._on_launched, channel, launch_error)

	#============================================

	def _on_launched(
		self, channel: tuner.models.Channel, launch_error: str | None
	) -> None:
		"""Show the launch result and return to the list (main thread).

		Args:
			channel: The channel that was launched.
			launch_error: None on success, or a concise error message on failure.
		"""
		if launch_error is None:
			# transient confirmation; the TUI stays on the list and fully live
			self._set_status(f"Launched {channel.guide_number} {channel.guide_name}")
		else:
			# launch-error state: concise message, no traceback
			self._set_status(f"Launch failed: {launch_error}")

	#============================================

	def action_favorite(self) -> None:
		"""Toggle favorite on the highlighted channel and re-sort the blocks."""
		channel = self._highlighted_channel()
		if channel is None:
			return
		# toggle keyed on GuideNumber so look-alike names stay independent
		self._state.toggle_favorite(channel.guide_number)
		# re-sort immediately, then keep the highlight on the same channel
		self._render_blocks(self._visible_channels)
		self._select_channel_by_guide_number(channel.guide_number)

	#============================================

	def action_refresh(self) -> None:
		"""Refresh the lineup from the device, re-reading live reception values."""
		# refresh only makes sense once a device is known
		if self._device is None:
			return
		self._set_status(f"Refreshing channels from {self._device.base_url}...")
		self._refresh_lineup()

	#============================================

	@textual.work(thread=True, exclusive=True)
	def _refresh_lineup(self) -> None:
		"""Re-fetch the lineup in a worker thread and re-render (main thread)."""
		channels = tuner.lineup.fetch_channels(self._device)
		# prune any channels that vanished from the lineup
		self._state.prune_to_lineup(channels)
		self.call_from_thread(self._on_refresh_ready, channels)

	#============================================

	def _on_refresh_ready(self, channels: list[tuner.models.Channel]) -> None:
		"""Re-render the list after a refresh (main thread).

		Args:
			channels: The freshly fetched channel lineup.
		"""
		self._render_blocks(channels)
		self._set_status(
			f"Ready - {self._device.friendly_name} ({len(channels)} channels)"
		)

#============================================

def run(host: str | None = None) -> None:
	"""Construct and run the HDHomeRun TUI.

	Args:
		host: Optional bare hostname or IP for the --host escape hatch.
	"""
	app = HDHRApp(host=host)
	app.run()
