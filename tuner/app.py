"""Textual TUI that discovers an HDHomeRun, lists channels, and launches mpv.

This module ties the data, state, and playback modules into a modeless,
zero-config channel picker.  The standard path is: run, auto-discover,
auto-fetch the lineup, sort into Favorites / All channels blocks, arrow +
Enter to launch mpv detached, and stay live.

Pure module-level helpers (format_guide_number, render_channel_row, and the
column-layout helpers) hold the row-rendering logic so it is unit-testable
without instantiating the app.
"""

# Standard Library
import textwrap

# PIP3 modules
import textual
import textual.app
import textual.binding
import textual.containers
import textual.screen
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

# Fixed column widths for columns that do not flex.
# Cursor: ">" or " " -- width 1
_CURSOR_WIDTH = 1
# Fav: "*" or " " -- width 1, but header title "Fav" is 3 chars; column width
# must accommodate the title.  Width 3 lets "Fav" fit and the marker stays
# left-aligned beneath it (padded with trailing spaces in both header and row).
_FAV_WIDTH = 3
# Alias: short user label like "CBS", "FOX"; 6 chars leaves room for 5-char labels
_ALIAS_WIDTH = 6
# Format: "1080i" or "720p" are both 5 chars; header "Format" is 6 -- use 6
_FORMAT_WIDTH = 6
# Quality / Strength: max value 100 (3 digits); header "Quality"=7, "Strength"=8
_QUALITY_WIDTH = 7
_STRENGTH_WIDTH = 8
# Plays: header "Plays" is 5 chars; counts rarely exceed 4 digits -- use 5
_PLAYS_WIDTH = 5

# Maximum total row width; Name column absorbs the remaining slack.
_MAX_ROW_WIDTH = 100

# Cap on name column width: let Name stay generous but bounded.
_NAME_WIDTH_CAP = 30

# Single space separator between every adjacent column pair.
_SEP = " "

# Arrow glyphs for the footer help bar, written as unicode escapes so the
# source file stays pure ASCII and passes test_ascii_compliance.
_UP_ARROW = "\u2191"
_DOWN_ARROW = "\u2193"

# Main-list footer help text.  Key tokens are accent-colored via Rich markup;
# action labels are dim.  The combined "Enter/p" token is one accent region.
_FOOTER_MAIN = (
	f"[bold cyan]{_UP_ARROW}/{_DOWN_ARROW}[/bold cyan][dim] move   [/dim]"
	"[bold cyan]Enter/p[/bold cyan][dim] play   [/dim]"
	"[bold cyan]f[/bold cyan][dim] favorite   [/dim]"
	"[bold cyan]a[/bold cyan][dim] alias   [/dim]"
	"[bold cyan]r[/bold cyan][dim] refresh   [/dim]"
	"[bold cyan]q[/bold cyan][dim] quit[/dim]"
)

# Alias-popup footer help text shown while the popup is open.  Only the popup
# keys are listed; the main-list keys are inactive while the popup owns focus.
_FOOTER_ALIAS = (
	"[bold cyan]Enter[/bold cyan][dim] save   [/dim]"
	"[bold cyan]Esc[/bold cyan][dim] cancel[/dim]"
)

#============================================

def reception_color(signal_quality: int | None) -> str:
	"""Pick a subtle color name for the Quality cell based on signal quality.

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

def name_width_for_channels(channels: list[tuner.models.Channel], cap: int) -> int:
	"""Compute the name column width from the channel set, bounded by a cap.

	The name column absorbs leftover space after fixed columns are allocated.
	This helper computes how much space is truly needed (longest name), but
	callers should also check against _remaining_name_width so the total row
	stays under _MAX_ROW_WIDTH.

	Args:
		channels: Visible channels whose guide names drive the minimum width.
		cap: Upper bound on the name column width.

	Returns:
		The character width of the widest guide name, clamped to [1, cap].
	"""
	width = 1
	for channel in channels:
		name_len = len(channel.guide_name)
		if name_len > width:
			width = name_len
	# clamp to cap
	if width > cap:
		width = cap
	return width

#============================================

def _remaining_name_width(major_width: int) -> int:
	"""Compute the name-column width that keeps total row width under _MAX_ROW_WIDTH.

	Column layout (each separated by _SEP=" "):
	  cursor(_CURSOR_WIDTH) sep fav(_FAV_WIDTH) sep Ch(major_width+3) sep
	  alias(_ALIAS_WIDTH) sep name(?) sep format(_FORMAT_WIDTH) sep
	  quality(_QUALITY_WIDTH) sep strength(_STRENGTH_WIDTH) sep plays(_PLAYS_WIDTH)

	The eight separators between nine columns account for one space each.
	The name column absorbs whatever is left.

	Args:
		major_width: The dot-justified guide-number major-part width.

	Returns:
		Characters available for the Name column (at least 1).
	"""
	# Ch column: major_width (major) + 1 (dot) + 2 (minor ljust(2))
	ch_width = major_width + 1 + 2
	# sum of all fixed column widths (everything except name)
	fixed_cols = (
		_CURSOR_WIDTH + _FAV_WIDTH + ch_width + _ALIAS_WIDTH
		+ _FORMAT_WIDTH + _QUALITY_WIDTH + _STRENGTH_WIDTH + _PLAYS_WIDTH
	)
	# 8 separators between the 9 columns (cursor/fav/ch/alias/name/format/quality/strength/plays)
	num_separators = 8
	fixed = fixed_cols + num_separators

	remaining = _MAX_ROW_WIDTH - fixed
	if remaining < 1:
		remaining = 1
	return remaining

#============================================

def _pad_text(text: str, width: int) -> str:
	"""Left-align text in a cell of exactly width characters, truncating if needed.

	Args:
		text: The text to fit in the cell.
		width: Target cell width in characters.

	Returns:
		A string of exactly width characters (padded with spaces or truncated).
	"""
	if len(text) > width:
		# truncate to width
		result = text[:width]
	else:
		# pad with trailing spaces
		result = text.ljust(width)
	return result

#============================================

def _num_cell(value: int | None, width: int) -> str:
	"""Right-align an integer in a cell of exactly width characters, or blank.

	Args:
		value: Integer to display, or None to show a blank cell.
		width: Target cell width in characters.

	Returns:
		A string of exactly width characters: right-aligned number or spaces.
	"""
	if value is None:
		return " " * width
	# right-align the number string to the cell width
	result = str(value).rjust(width)
	return result

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

def column_header_line(major_width: int, name_width: int, alias_width: int) -> str:
	"""Build the dim column-header text aligned to the same widths the rows use.

	Uses the identical column ordering and separator (_SEP) as render_channel_row
	so header and data rows share a single layout source of truth.

	Column order: cursor, fav, Ch, alias, name, format, quality, strength, plays.
	The cursor column header is blank (no title for the ">" indicator).
	The fav column is width _FAV_WIDTH=3 so the title "Fav" fits exactly.
	All numeric columns (format, quality, strength, plays) are right-aligned.
	Text columns (alias, name) are left-aligned.

	Args:
		major_width: Major-part width for the Ch column (from major_width_for_channels).
		name_width: Name column width (from name_width_for_channels clamped to budget).
		alias_width: Alias column width (fixed _ALIAS_WIDTH).

	Returns:
		A plain-text header string with column titles at the right positions,
		wrapped in dim markup.
	"""
	# Ch column width: major digits + dot + 2 minor digits
	ch_col_width = major_width + 1 + 2

	# Build header cells using the exact same column order and separator as render_channel_row.
	# cursor column: blank (no title for the ">" marker)
	cursor_cell = " " * _CURSOR_WIDTH
	# fav column: left-aligned "Fav" in _FAV_WIDTH (width 3, so it fits exactly)
	fav_cell = _pad_text("Fav", _FAV_WIDTH)
	# Ch column: right-align "Ch" over the dot-justified guide number
	ch_cell = "Ch".rjust(ch_col_width)
	# alias column: left-aligned title
	alias_cell = _pad_text("Alias", alias_width)
	# name column: left-aligned title
	name_cell = _pad_text("Name", name_width)
	# format column: right-aligned title
	format_cell = "Format".rjust(_FORMAT_WIDTH)
	# quality column: right-aligned title
	quality_cell = "Quality".rjust(_QUALITY_WIDTH)
	# strength column: right-aligned title
	strength_cell = "Strength".rjust(_STRENGTH_WIDTH)
	# plays column: right-aligned title
	plays_cell = "Plays".rjust(_PLAYS_WIDTH)

	# join with the same single-space separator (_SEP) used in render_channel_row
	header = _SEP.join([
		cursor_cell,
		fav_cell,
		ch_cell,
		alias_cell,
		name_cell,
		format_cell,
		quality_cell,
		strength_cell,
		plays_cell,
	])

	# wrap the whole line in dim markup
	dim_header = f"[dim]{header}[/dim]"
	return dim_header

#============================================

def render_channel_row(
	channel: tuner.models.Channel,
	major_width: int,
	name_width: int,
	alias_width: int,
	is_cursor: bool,
	is_favorite: bool,
	alias_label: str | None,
	format_label: str | None,
	play_count: int,
) -> str:
	"""Build the Textual-markup label text for one wide fixed-column channel row.

	Layout left to right: cursor, fav marker, dot-justified Ch, Alias, Name,
	Format, Quality, Strength, Plays.  All columns hold fixed widths so the
	header stays aligned regardless of content.

	Args:
		channel: The channel to render (supplies guide_number, guide_name,
			signal_quality, signal_strength).
		major_width: Major-part width for dot-justification.
		name_width: Name column width in characters.
		alias_width: Alias column width in characters.
		is_cursor: True to show '>' in the cursor column, False for space.
		is_favorite: True to show '*' in the Fav column.
		alias_label: Short alias label (e.g. 'CBS'), or None when unset.
		format_label: Cached format label (e.g. '1080i'), or None when uncached.
		play_count: Play count; zero renders as blank.

	Returns:
		A single line of Textual markup for a ListItem label.
	"""
	# cursor column: ">" for the highlighted row, space otherwise; width _CURSOR_WIDTH=1
	cursor_cell = ">" if is_cursor else " "

	# fav column: left-aligned "*" or " " in _FAV_WIDTH=3 so it aligns under "Fav" title
	fav_marker = "*" if is_favorite else " "
	fav_cell = _pad_text(fav_marker, _FAV_WIDTH)

	# Ch column: dot-justified guide number (major_width + dot + 2 minor digits)
	ch_cell = format_guide_number(channel.guide_number, major_width)

	# alias cell: left-aligned, blank when None
	alias_cell = _pad_text(alias_label if alias_label is not None else "", alias_width)

	# name cell: escape markup chars, then pad/truncate to name_width
	raw_name = _escape_markup(channel.guide_name)
	name_cell = _pad_text(raw_name, name_width)

	# format cell: right-aligned label in _FORMAT_WIDTH, spaces when None
	format_raw = format_label if format_label is not None else ""
	format_cell = format_raw.rjust(_FORMAT_WIDTH)

	# quality cell: right-aligned number, spaces when None; color markup added below
	quality_color = reception_color(channel.signal_quality)
	quality_plain = _num_cell(channel.signal_quality, _QUALITY_WIDTH)
	# wrap quality in color markup (does not consume display width)
	quality_cell = f"[{quality_color}]{quality_plain}[/{quality_color}]"

	# strength cell: right-aligned number, spaces when None; no color
	strength_cell = _num_cell(channel.signal_strength, _STRENGTH_WIDTH)

	# plays cell: right-aligned count, spaces when zero
	plays_value: int | None = play_count if play_count > 0 else None
	plays_cell = _num_cell(plays_value, _PLAYS_WIDTH)

	# join cells with a single-space separator -- matches column_header_line exactly
	row = _SEP.join([
		cursor_cell,
		fav_cell,
		ch_cell,
		alias_cell,
		name_cell,
		format_cell,
		quality_cell,
		strength_cell,
		plays_cell,
	])
	return row

#============================================

class AliasPopup(textual.screen.ModalScreen):
	"""Small modal popup for editing the alias label of one channel.

	Opens when the user presses 'a' on a channel row.  Contains a short info
	label naming the channel and a single Input widget prefilled with the
	current alias.  Enter saves; Esc cancels.  While open it owns the keyboard
	so main-list bindings (play, favorite, quit, etc.) do not fire.
	"""

	# Minimal CSS to size and centre the popup panel.
	DEFAULT_CSS = """
	AliasPopup {
		align: center middle;
	}
	AliasPopup > #alias_panel {
		width: 50;
		height: auto;
		padding: 1 2;
		background: $surface;
		border: solid $primary;
	}
	AliasPopup > #alias_panel > #alias_help {
		height: 1;
		color: $text-muted;
	}
	"""

	# Esc dismisses without saving; no other bindings needed because the Input
	# widget handles Enter natively via its Submitted message.
	BINDINGS = [
		textual.binding.Binding("escape", "dismiss_cancel", "cancel", show=False),
	]

	def __init__(
		self,
		guide_number: str,
		guide_name: str,
		current_alias: str | None,
	) -> None:
		"""Initialise the popup.

		Args:
			guide_number: Guide number of the channel being edited (e.g. '7.1').
			guide_name: Display name of the channel (e.g. 'WLS-HD').
			current_alias: The existing alias to prefill the input, or None.
		"""
		super().__init__()
		# channel identity fields used to label the popup and return the result
		self._guide_number = guide_number
		self._guide_name = guide_name
		# prefill value; empty string when no alias is set yet
		self._current_alias = current_alias if current_alias is not None else ""

	#============================================

	def compose(self) -> textual.app.ComposeResult:
		"""Build the popup widget tree: info label, input, help line.

		Returns:
			The Textual compose result yielding the popup's widgets.
		"""
		with textual.containers.Container(id="alias_panel"):
			# info label: names the channel so the user knows what they are editing
			info_text = (
				f"[bold]{self._guide_number}[/bold] "
				f"{_escape_markup(self._guide_name)}"
			)
			yield textual.widgets.Label(info_text, id="alias_info")
			# single text input; prefilled with the current alias (empty if none)
			yield textual.widgets.Input(
				value=self._current_alias,
				placeholder="alias (empty to clear)",
				id="alias_input",
			)
			# one-line help: accent Enter and Esc, dim action labels
			yield textual.widgets.Static(_FOOTER_ALIAS, id="alias_help")

	#============================================

	def on_mount(self) -> None:
		"""Focus the Input widget as soon as the popup is mounted."""
		# direct focus to the input so the user can type immediately
		self.query_one("#alias_input", textual.widgets.Input).focus()

	#============================================

	def on_input_submitted(self, event: textual.widgets.Input.Submitted) -> None:
		"""Handle Enter in the Input: dismiss and return the entered value.

		An empty value signals an alias clear; the caller handles that via
		state.set_alias which treats an empty string as a delete.

		Args:
			event: The Input.Submitted message carrying the final value.
		"""
		# return the stripped value to the caller via dismiss
		self.dismiss(event.value.strip())

	#============================================

	def action_dismiss_cancel(self) -> None:
		"""Dismiss the popup without saving (Esc path)."""
		# None signals cancel to the callback in HDHRApp.action_alias
		self.dismiss(None)


#============================================

class HDHRApp(textual.app.App):
	"""Textual app for the HDHomeRun OTA channel launcher.

	The app moves through a small explicit set of screen states (discovering,
	loading-lineup, ready, launching, launched, launch-error, error) surfaced in
	a status line above the channel list.  There is exactly one interactive mode:
	the channel list.  The same keys always mean the same thing and q always
	quits, so the user never gets stuck.
	"""

	# CSS keeps the status line, header, and footer visually distinct from the list.
	# The highlight-bar suppression targets the .-highlight pseudo-class that Textual
	# adds to the focused ListItem; both the focused (ListView:focus) and blurred
	# variants are reset so the ">" cursor glyph is the only selection indicator.
	CSS = textwrap.dedent(
		"""
		#status {
			height: auto;
			padding: 0 1;
			color: $text;
		}
		#col_header {
			height: 1;
			padding: 0 1;
			color: $text-muted;
		}
		#channel_list {
			height: 1fr;
		}
		/* Suppress the default full-width highlighted-row background.
		   Textual 8.x uses .-highlight on the ListItem for the selection bar;
		   we clear background, foreground override, and text-style so the row
		   reads exactly like un-highlighted rows and only the ">" glyph stands out. */
		#channel_list > ListItem.-highlight {
			background: transparent;
			color: $foreground;
			text-style: none;
		}
		/* Also suppress the focused-state variant, which is the primary bar. */
		#channel_list:focus > ListItem.-highlight {
			background: transparent;
			color: $foreground;
			text-style: none;
		}
		/* Dim the .block-header section-header rows so they read as labels, not data. */
		.block-header {
			color: $text-muted;
		}
		#footer {
			height: 1;
			padding: 0 1;
			border-top: solid $panel-lighten-1;
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
		textual.binding.Binding("a", "alias", "alias"),
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
		# computed name column width for the visible set
		self._name_width = _NAME_WIDTH_CAP

	#============================================

	def compose(self) -> textual.app.ComposeResult:
		"""Build the widget tree: status line, column header, channel list, footer.

		Returns:
			The Textual compose result yielding the app's widgets.
		"""
		# status line communicates the current screen state to the user
		yield textual.widgets.Static("Looking for HDHomeRun...", id="status")
		# persistent dim column header; rebuilt after lineup load and refresh
		yield textual.widgets.Static("", id="col_header")
		# the single channel list; Up/Down move the highlight natively
		yield textual.widgets.ListView(id="channel_list")
		# persistent footer of the main key bindings, accent-colored key tokens
		yield textual.widgets.Static(_FOOTER_MAIN, id="footer")

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

	def _rebuild_header(self) -> None:
		"""Rebuild the column header Static to match the current column widths."""
		header_text = column_header_line(
			self._major_width, self._name_width, _ALIAS_WIDTH
		)
		col_header = self.query_one("#col_header", textual.widgets.Static)
		col_header.update(header_text)

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
		# render in a worker so the awaited clear() runs before the rows are extended
		self.run_worker(self._rerender(channels), group="render", exclusive=True)
		self._set_status(f"Ready - {device.friendly_name} ({len(channels)} channels)")

	#============================================

	async def _render_blocks(self, channels: list[tuner.models.Channel]) -> None:
		"""Sort channels into two blocks and (re)populate the ListView.

		Empty blocks are hidden (no header is shown for them).  The highlight is
		left at the top after a full render; callers that need to preserve the
		highlight handle that separately.

		Args:
			channels: The full channel lineup to sort and display.
		"""
		# state is set once the lineup is ready; guard like _repaint_cursor so a
		# stray render before load is a no-op rather than an AttributeError
		if self._state is None:
			return
		state = self._state
		favorites, all_channels = state.sort_blocks(channels)

		# the visible set is the concatenation of the two blocks, in order
		visible: list[tuner.models.Channel] = []
		visible.extend(favorites)
		visible.extend(all_channels)
		self._visible_channels = visible
		self._major_width = major_width_for_channels(visible)

		# name column width: clamped to the layout budget and the name-width cap
		content_name_width = name_width_for_channels(visible, _NAME_WIDTH_CAP)
		budget_name_width = _remaining_name_width(self._major_width)
		self._name_width = min(content_name_width, budget_name_width)
		if self._name_width < 1:
			self._name_width = 1

		# build all items first, then mutate the DOM in two awaited steps
		items = self._build_block_items("Favorites", favorites)
		items.extend(self._build_block_items("All channels", all_channels))

		list_view = self.query_one("#channel_list", textual.widgets.ListView)
		# clear() and extend() are asynchronous: await each so the old rows leave the
		# DOM before the new rows are added, otherwise re-renders collide on duplicate
		# ListItem ids (e.g. "ch_2_1") and Textual raises DuplicateIds
		await list_view.clear()
		await list_view.extend(items)

	#============================================

	async def _rerender(
		self,
		channels: list[tuner.models.Channel],
		select_guide: str | None = None,
	) -> None:
		"""Re-render the blocks, rebuild the header, restore selection, paint cursor.

		Runs as a worker coroutine so the awaited ListView.clear() completes before
		rows are re-appended.  Sync handlers launch this via run_worker.

		Args:
			channels: The channel lineup to render.
			select_guide: Guide number to re-highlight after the render, or None to
				leave the highlight at the top.
		"""
		await self._render_blocks(channels)
		self._rebuild_header()
		# the first list item is the disabled block header, so the highlight must be
		# moved onto a real channel row: a header-highlighted state is never valid UX.
		# Restore the requested channel when possible; otherwise default to the first
		# visible channel.  _visible_channels is favorites followed by all channels, so
		# index 0 is the first favorite when any favorites exist and the first channel
		# otherwise -- exactly the desired default.  The guide number is read from the
		# data, never assumed, so no specific channel (e.g. 2.1) is hard-coded.
		restored = False
		if select_guide is not None:
			restored = self._select_channel_by_guide_number(select_guide)
		if not restored and self._visible_channels:
			self._select_channel_by_guide_number(self._visible_channels[0].guide_number)
		# paint the ">" cursor on the highlighted row after the re-render
		self._repaint_cursor()

	#============================================

	def _row_markup(
		self,
		channel: tuner.models.Channel,
		is_cursor: bool,
		favorites: frozenset,
		play_counts: dict,
	) -> str:
		"""Assemble the markup for one channel row from current state.

		Shared by _build_block_items (initial build) and _repaint_cursor (cursor
		repaint) so the per-row column data is gathered in exactly one place and
		the two paths cannot drift apart when a column is added.

		Args:
			channel: The channel to render.
			is_cursor: True to show the ">" cursor on this row.
			favorites: The current favorites set (prefetched once by the caller).
			play_counts: The current play-count map (prefetched once by the caller).

		Returns:
			The Textual-markup text for the row's Label.
		"""
		is_favorite = channel.guide_number in favorites
		# play count is genuinely optional: zero for channels never played
		play_count = play_counts.get(channel.guide_number, 0)
		# format label is None until the channel is launched and probed once
		format_label = self._state.format_label(channel.guide_number)
		# alias is None unless the user set one in the popup
		alias_label = self._state.alias(channel.guide_number)
		row_text = render_channel_row(
			channel=channel,
			major_width=self._major_width,
			name_width=self._name_width,
			alias_width=_ALIAS_WIDTH,
			is_cursor=is_cursor,
			is_favorite=is_favorite,
			alias_label=alias_label,
			format_label=format_label,
			play_count=play_count,
		)
		return row_text

	#============================================

	def _build_block_items(
		self,
		title: str,
		channels: list[tuner.models.Channel],
	) -> list[textual.widgets.ListItem]:
		"""Build the ListItems for one block: a dim header plus its channel rows.

		Empty blocks return an empty list so first run shows only All channels.

		Args:
			title: The block header text.
			channels: The channels in this block (already sorted).

		Returns:
			ListItems for this block (header first, then one per channel), or an
			empty list when the block has no channels.
		"""
		# hide empty blocks: no header, no rows
		if not channels:
			return []

		items: list[textual.widgets.ListItem] = []
		# header row is disabled so it cannot be highlighted or selected
		header_label = textual.widgets.Label(f"[dim][b]{title}[/b][/dim]")
		header_item = textual.widgets.ListItem(header_label, disabled=True)
		header_item.add_class("block-header")
		items.append(header_item)

		# prefetch the favorites set and play-count map once for the whole block
		state = self._state
		play_counts = state.play_counts
		favorites = state.favorites
		for channel in channels:
			# cursor is not set at build time; _repaint_cursor handles it after mount
			row_text = self._row_markup(channel, False, favorites, play_counts)
			row_label = textual.widgets.Label(row_text)
			# id encodes the guide number so selection maps back to a channel;
			# dots are not valid in ids, so encode them as underscores
			row_id = "ch_" + channel.guide_number.replace(".", "_")
			items.append(textual.widgets.ListItem(row_label, id=row_id))
		return items

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

	def _select_channel_by_guide_number(self, guide_number: str) -> bool:
		"""Move the highlight to the row matching a guide number, if present.

		Used after a favorite toggle re-sorts the blocks so the highlight stays
		on the same channel.

		Args:
			guide_number: The guide number to re-highlight.

		Returns:
			True when a matching channel row was found and highlighted, False
			when no row matched (e.g. the channel left the lineup).
		"""
		list_view = self.query_one("#channel_list", textual.widgets.ListView)
		target_id = "ch_" + guide_number.replace(".", "_")
		for index, item in enumerate(list_view.children):
			if item.id == target_id:
				list_view.index = index
				return True
		return False

	#============================================

	def _repaint_cursor(self) -> None:
		"""Repaint the cursor cell (">" or " ") on every visible channel row.

		Walks the ListView's children, identifies channel rows by their "ch_"
		id prefix, and re-renders each row's Label with is_cursor set only for
		the row matching the currently highlighted item.  Block-header rows
		(disabled, no "ch_" id) are skipped entirely.

		Called after every highlight change (on_list_view_highlighted), after a
		favorite-toggle re-sort, after an alias save re-render, and after the
		initial lineup render so the first row shows the cursor immediately.
		"""
		list_view = self.query_one("#channel_list", textual.widgets.ListView)
		highlighted = list_view.highlighted_child

		# determine which row id currently holds the cursor (may be None)
		highlighted_id: str | None = None
		if highlighted is not None and highlighted.id is not None:
			if highlighted.id.startswith("ch_"):
				highlighted_id = highlighted.id

		# build a lookup: guide_number -> Channel for quick per-row access
		channel_by_guide: dict[str, tuner.models.Channel] = {}
		for channel in self._visible_channels:
			channel_by_guide[channel.guide_number] = channel

		# we need state for per-row data; if state is not ready yet, nothing to paint
		if self._state is None:
			return

		state = self._state
		play_counts = state.play_counts
		favorites = state.favorites

		# walk every item in the list; only process channel rows (id starts with "ch_")
		for item in list_view.children:
			if item.id is None or not item.id.startswith("ch_"):
				# block-header or non-channel item -- skip
				continue
			# decode the guide number from the row id (e.g. "ch_24_10" -> "24.10")
			guide_number = item.id[len("ch_"):].replace("_", ".")
			channel = channel_by_guide.get(guide_number)
			if channel is None:
				# stale row (channel vanished from visible set) -- skip
				continue

			# determine cursor state for this row, then re-render via the shared helper
			is_cursor = item.id == highlighted_id
			row_text = self._row_markup(channel, is_cursor, favorites, play_counts)
			# update the Label inside the ListItem
			label = item.query_one(textual.widgets.Label)
			label.update(row_text)

	#============================================

	def on_list_view_highlighted(
		self, event: textual.widgets.ListView.Highlighted
	) -> None:
		"""Repaint the cursor glyph when the ListView highlight moves.

		Args:
			event: The ListView.Highlighted message (unused; we query the widget).
		"""
		# repaint so ">" follows the new highlighted row
		self._repaint_cursor()

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
		"""Play the highlighted channel: record, probe format, launch detached."""
		channel = self._highlighted_channel()
		# nothing to do on status screens or empty selection
		if channel is None:
			return
		state = self._state
		# record the selection immediately so play counts reflect intent
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
		"""Detect stream format (cached), then launch mpv detached, in a thread.

		Reads the cached format label from state; when absent, runs probe_format
		and caches a non-empty result.  Derives the interlace decision via
		interlace_for_playback so a blank label falls back to the known-interlaced
		table and playback always works.

		Args:
			channel: The channel to probe and launch.
		"""
		# use the cached format label when present; avoids re-probing on repeat launches
		label = self._state.format_label(channel.guide_number)
		if label is None:
			# first launch for this channel: probe off the event loop
			label = tuner.playback.probe_format(channel.stream_url, channel.guide_number)
			if label:
				# only cache confident, non-empty labels; blank means probe failed
				self._state.set_format(channel.guide_number, label)
			# when label is still empty string, interlace_for_playback falls back
			# to KNOWN_INTERLACED_GUIDE_NUMBERS so playback still works correctly

		# label is now always a string: a cached label, a fresh probe result, or ""
		# from a failed probe.  An empty label makes interlace_for_playback fall back
		# to KNOWN_INTERLACED_GUIDE_NUMBERS so playback still works correctly.
		interlaced = tuner.playback.interlace_for_playback(label, channel.guide_number)
		# launch detached; a non-None return is a concise launch-time error
		launch_error = tuner.playback.launch(channel, interlaced)
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
		# re-sort in a worker (awaited clear), then keep the highlight on this channel
		self.run_worker(
			self._rerender(self._visible_channels, select_guide=channel.guide_number),
			group="render",
			exclusive=True,
		)

	#============================================

	def action_alias(self) -> None:
		"""Open the alias popup for the highlighted channel.

		Does nothing when the highlight is on a section header or when no channel
		is highlighted (status screens, empty list).  While the popup is open it
		owns the keyboard via ModalScreen; list bindings do not fire and 'q' does
		not quit.  After the popup closes on save, re-renders the list so the
		Alias cell updates immediately, and restores the highlight to the same
		channel.
		"""
		channel = self._highlighted_channel()
		# no-op on headers (disabled items without a channel id) or empty list
		if channel is None:
			return
		# snapshot the guide number before pushing the modal (the render may shift indices)
		guide_number = channel.guide_number
		guide_name = channel.guide_name
		current_alias = self._state.alias(guide_number)

		# switch the footer to show the popup's keys while the modal is open
		footer = self.query_one("#footer", textual.widgets.Static)
		footer.update(_FOOTER_ALIAS)

		def _on_alias_dismiss(result: str | None) -> None:
			"""Handle the popup result after it closes.

			Args:
				result: The stripped alias string on save (may be empty to clear),
					or None when the user pressed Esc to cancel.
			"""
			# restore the main-list help bar regardless of save/cancel
			footer.update(_FOOTER_MAIN)
			if result is None:
				# Esc cancel: no state change, no re-render needed
				return
			# save the alias (empty string clears it via set_alias)
			self._state.set_alias(guide_number, result)
			# re-render in a worker (awaited clear) so the Alias cell updates and the
			# highlight returns to the same channel without colliding on row ids
			self.run_worker(
				self._rerender(self._visible_channels, select_guide=guide_number),
				group="render",
				exclusive=True,
			)

		popup = AliasPopup(guide_number, guide_name, current_alias)
		self.push_screen(popup, _on_alias_dismiss)

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
		# render in a worker so the awaited clear() runs before the rows are extended
		self.run_worker(self._rerender(channels), group="render", exclusive=True)
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
