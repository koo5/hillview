"""Unit tests for /bestof page → offset arithmetic.

The invariant worth pinning: consecutive pages tile the ranking exactly. If the
slice size and the step between slices ever diverge, nothing raises — a step
under the size repeats photos across pages, and a step over it leaves photos
that NO page lists, so they are unreachable by a crawler and the loss is
invisible in the UI.
"""
import pytest

from bestof_routes import BESTOF_PAGE_SIZE, page_offset


def test_consecutive_pages_tile_with_no_overlap_and_no_gap():
	for page in range(1, 26):
		assert page_offset(page + 1) == page_offset(page) + BESTOF_PAGE_SIZE


def test_first_page_starts_at_the_top():
	assert page_offset(1) == 0


@pytest.mark.parametrize("bad", [None, 0, -1, -100])
def test_junk_and_out_of_range_mean_the_first_page(bad):
	assert page_offset(bad) == 0


def test_offsets_are_whole_rows():
	for page in range(1, 26):
		assert isinstance(page_offset(page), int)
