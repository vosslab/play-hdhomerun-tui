"""Tests for the pure guide-number formatting helper in tuner.app.

Covers dot-justification only: the decimal point lands in the same column
regardless of how many digits the major part has.  No TUI, colors, or layout
are asserted -- those are decoration verified by eye, not pytest.
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
