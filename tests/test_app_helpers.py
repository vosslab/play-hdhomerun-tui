"""Tests for pure helper functions in tuner.app.

Covers:
  - format_guide_number: dot-justification so decimal points align in a column.
  - _pad_text: left-align text in a fixed-width cell (pad and truncate).
  - _num_cell: right-align an int (or blank when None) in a fixed-width cell.

No TUI, Textual widgets, colors, CSS, or full-row render output is asserted;
those are visual properties verified by manual E2E.
"""

# local repo modules
import tuner.app

#============================================

def test_guide_number_dot_aligns_across_major_widths() -> None:
	"""Single- and double-digit majors put the dot in the same column."""
	narrow = tuner.app.format_guide_number("7.1", 2)
	wide = tuner.app.format_guide_number("11.1", 2)
	assert narrow.index(".") == wide.index(".")

#============================================

def test_guide_number_keeps_both_parts() -> None:
	"""A two-digit sub-channel keeps both the major and minor digits."""
	out = tuner.app.format_guide_number("24.10", 2)
	assert "24" in out
	assert "10" in out

#============================================

def test_pad_text_truncates_long_string() -> None:
	"""_pad_text truncates a string longer than the cap to exactly width chars."""
	result = tuner.app._pad_text("LongChannelName", 8)
	assert len(result) == 8

#============================================

def test_pad_text_pads_short_string() -> None:
	"""_pad_text left-pads a short string to exactly width chars with spaces."""
	result = tuner.app._pad_text("CBS", 8)
	assert len(result) == 8
	assert result.startswith("CBS")

#============================================

def test_num_cell_right_aligns_int() -> None:
	"""_num_cell right-aligns an int to the given width."""
	result = tuner.app._num_cell(80, 7)
	assert len(result) == 7
	# leading spaces pad to fill width; strip them to check the number content
	assert result.lstrip() == "80"

#============================================

def test_num_cell_none_yields_blank() -> None:
	"""_num_cell renders a blank cell (no digits) when value is None."""
	result = tuner.app._num_cell(None, 7)
	assert result.strip() == ""

#============================================

def test_reception_color_buckets_at_thresholds() -> None:
	"""reception_color buckets quality by the 60 and 80 thresholds.

	Asserts bucket membership and distinctness rather than exact color names, so a
	threshold off-by-one is caught without coupling the test to specific colors.
	"""
	# values on the same side of a threshold share a color
	assert tuner.app.reception_color(80) == tuner.app.reception_color(100)
	assert tuner.app.reception_color(60) == tuner.app.reception_color(79)
	assert tuner.app.reception_color(0) == tuner.app.reception_color(59)
	# the three quality buckets are visually distinct from one another
	assert tuner.app.reception_color(80) != tuner.app.reception_color(79)
	assert tuner.app.reception_color(60) != tuner.app.reception_color(59)
	assert tuner.app.reception_color(80) != tuner.app.reception_color(0)
