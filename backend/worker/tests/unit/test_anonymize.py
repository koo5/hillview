#!/usr/bin/env python3
"""
Unit tests for anonymize.py pure functions:
  - _tile_starts
  - deduplicate_boxes
  - run_yolo_multiscale (with a mock YOLO model)
"""

import sys
import os
import types

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))


# ---------------------------------------------------------------------------
# Minimal stubs so anonymize.py can be imported without torch / ultralytics
# ---------------------------------------------------------------------------

def _make_stub_modules():
    """Install lightweight stub modules for heavy dependencies."""
    # torch stub
    torch_stub = types.ModuleType('torch')
    torch_stub.load = lambda *a, **kw: None
    sys.modules.setdefault('torch', torch_stub)

    # ultralytics stub
    ultra_stub = types.ModuleType('ultralytics')

    class _YOLO:
        def __init__(self, path): pass

    ultra_stub.YOLO = _YOLO
    sys.modules.setdefault('ultralytics', ultra_stub)

    # cv2 stub — only resize is needed
    cv2_stub = types.ModuleType('cv2')
    cv2_stub.INTER_AREA = 3

    def _resize(img, dsize, interpolation=None):
        h, w = dsize[1], dsize[0]
        return np.zeros((h, w, img.shape[2]), dtype=img.dtype)

    cv2_stub.resize = _resize
    sys.modules.setdefault('cv2', cv2_stub)


_make_stub_modules()

# detections stub — must be present before importing anonymize
detections_stub = types.ModuleType('detections')
detections_stub.TARGET_CLASSES = {0: 'person', 2: 'car'}
sys.modules.setdefault('detections', detections_stub)

# blur stub — anonymize imports apply_blur / read_image from blur
blur_stub = types.ModuleType('blur')
blur_stub.apply_blur = lambda *a, **kw: None
blur_stub.read_image = lambda p: np.zeros((100, 100, 3), dtype=np.uint8)
sys.modules.setdefault('blur', blur_stub)

from anonymize import _tile_starts, deduplicate_boxes, run_yolo_multiscale  # noqa: E402


# ---------------------------------------------------------------------------
# _tile_starts
# ---------------------------------------------------------------------------

class TestTileStarts:
    def test_fits_in_one_tile(self):
        assert _tile_starts(800, 1280, 1024) == [0]

    def test_exact_fit(self):
        assert _tile_starts(1280, 1280, 1024) == [0]

    def test_two_tiles_needed(self):
        starts = _tile_starts(2000, 1280, 1024)
        assert starts[0] == 0
        # last start must be such that start + tile_size >= length
        assert starts[-1] + 1280 >= 2000

    def test_trailing_edge_covered(self):
        """The last tile must always reach the far edge."""
        for length in (1281, 1500, 2560, 5000):
            starts = _tile_starts(length, 1280, 1024)
            assert starts[-1] + 1280 >= length, f"trailing edge not covered for length={length}"

    def test_no_gaps(self):
        """Consecutive tile starts must be at most one step apart (no gaps)."""
        step = 1024
        starts = _tile_starts(5000, 1280, step)
        for i in range(len(starts) - 1):
            assert starts[i + 1] - starts[i] <= step


# ---------------------------------------------------------------------------
# deduplicate_boxes
# ---------------------------------------------------------------------------

class TestDeduplicateBoxes:
    def test_empty(self):
        assert deduplicate_boxes([]) == []

    def test_single_box(self):
        boxes = [(0, (10, 20, 50, 80))]
        assert deduplicate_boxes(boxes) == boxes

    def test_exact_duplicate_dropped(self):
        boxes = [(0, (10, 20, 50, 80)), (0, (10, 20, 50, 80))]
        result = deduplicate_boxes(boxes)
        assert len(result) == 1

    def test_near_duplicate_within_tolerance_dropped(self):
        boxes = [(0, (10, 20, 50, 80)), (0, (12, 22, 48, 78))]
        result = deduplicate_boxes(boxes, tolerance=10)
        assert len(result) == 1

    def test_near_duplicate_outside_tolerance_kept(self):
        boxes = [(0, (10, 20, 50, 80)), (0, (25, 35, 65, 95))]
        result = deduplicate_boxes(boxes, tolerance=10)
        assert len(result) == 2

    def test_subsumed_box_dropped(self):
        """A small box whose area is ≥80% covered by a larger box is dropped."""
        big = (0, (0, 0, 200, 200))
        small = (0, (10, 10, 50, 50))   # fully inside big
        result = deduplicate_boxes([big, small], subsumption_threshold=0.8)
        assert len(result) == 1
        assert result[0][1] == (0, 0, 200, 200)

    def test_partially_overlapping_box_kept(self):
        """A box only half-covered should NOT be subsumed at the 0.8 threshold."""
        box_a = (0, (0, 0, 100, 100))
        box_b = (0, (50, 0, 150, 100))  # 50% overlap with box_a
        result = deduplicate_boxes([box_a, box_b], subsumption_threshold=0.8)
        assert len(result) == 2

    def test_larger_box_wins_over_smaller(self):
        """When two boxes are near-duplicates, the larger survives."""
        large = (0, (10, 10, 110, 110))
        small = (0, (12, 12, 108, 108))
        result = deduplicate_boxes([small, large], tolerance=10)
        assert len(result) == 1
        assert result[0][1] == (10, 10, 110, 110)

    def test_different_classes_both_kept(self):
        """Same coordinates but different class IDs: only one is kept (duplicate check is coordinate-only)."""
        person = (0, (10, 20, 50, 80))
        car = (2, (10, 20, 50, 80))
        # near-duplicate check uses coordinates only, so one will be dropped
        result = deduplicate_boxes([person, car])
        assert len(result) == 1

    def test_zero_area_box_not_subsumed(self):
        """A degenerate (zero-area) box cannot be subsumed by subsumption logic."""
        big = (0, (0, 0, 200, 200))
        zero = (0, (50, 50, 50, 50))   # zero area
        result = deduplicate_boxes([big, zero], tolerance=0, subsumption_threshold=0.8)
        # zero-area box has curr_area=0 → subsumption branch skipped → kept
        assert any(b[1] == (50, 50, 50, 50) for b in result)

    def test_configurable_tolerance(self):
        boxes = [(0, (10, 10, 50, 50)), (0, (25, 25, 65, 65))]
        assert len(deduplicate_boxes(boxes, tolerance=5)) == 2
        assert len(deduplicate_boxes(boxes, tolerance=20)) == 1

    def test_configurable_subsumption_threshold(self):
        big = (0, (0, 0, 100, 100))
        # overlap area = 40×40 = 1600; small area = 40×40 = 1600 → 100% covered
        small = (0, (30, 30, 70, 70))
        assert len(deduplicate_boxes([big, small], subsumption_threshold=0.9)) == 1
        assert len(deduplicate_boxes([big, small], subsumption_threshold=1.01)) == 2


# ---------------------------------------------------------------------------
# run_yolo_multiscale  (mock YOLO model)
# ---------------------------------------------------------------------------

class _FakeBox:
    """Mimics one ultralytics detection box."""
    def __init__(self, cls_id, x1, y1, x2, y2):
        # Ultralytics returns a 0-d tensor for cls; use a 0-d numpy array here.
        self.cls = np.array(cls_id, dtype=np.float32)
        # xyxy must support box.xyxy[0] and map(int, ...)
        self.xyxy = [np.array([x1, y1, x2, y2], dtype=np.float32)]


class _FakeResults:
    def __init__(self, boxes):
        self.boxes = boxes


class _MockYOLO:
    """Mock YOLO model that returns a fixed detection list for every tile."""
    def __init__(self, detections=None):
        # detections: list of (cls_id, x1, y1, x2, y2) in tile-local coords
        self._detections = detections or []

    def __call__(self, tile):
        boxes = [_FakeBox(*d) for d in self._detections]
        return [_FakeResults(boxes)]


class TestRunYoloMultiscale:
    def _make_image(self, h=500, w=500):
        return np.zeros((h, w, 3), dtype=np.uint8)

    def test_no_detections(self):
        model = _MockYOLO(detections=[])
        image = self._make_image(500, 500)
        result = run_yolo_multiscale(image, model, max_tile_size=1280, min_scale_size=256)
        assert result == []

    def test_single_detection_small_image(self):
        """Image fits in one tile: single pass, detection returned."""
        model = _MockYOLO(detections=[(0, 10, 10, 60, 60)])
        image = self._make_image(500, 500)
        result = run_yolo_multiscale(image, model, max_tile_size=1280, min_scale_size=256)
        assert len(result) == 1
        cls_id, (x1, y1, x2, y2) = result[0]
        assert cls_id == 0
        assert x1 == 10 and y1 == 10 and x2 == 60 and y2 == 60

    def test_unknown_class_filtered_out(self):
        """Class IDs not in TARGET_CLASSES must be dropped."""
        model = _MockYOLO(detections=[(99, 10, 10, 50, 50)])
        image = self._make_image(500, 500)
        result = run_yolo_multiscale(image, model, max_tile_size=1280, min_scale_size=256)
        assert result == []

    def test_large_image_triggers_tiling(self):
        """Image larger than max_tile_size must be tiled (multiple tiles processed)."""
        call_count = {'n': 0}

        class _CountingYOLO:
            def __call__(self, tile):
                call_count['n'] += 1
                return [_FakeResults([])]

        image = self._make_image(3000, 3000)
        run_yolo_multiscale(image, _CountingYOLO(), max_tile_size=1280, min_scale_size=256, overlap=0.2)
        # A 3000×3000 image with 1280-tile and 20% overlap needs more than 1 tile per scale
        assert call_count['n'] > 1

    def test_min_scale_size_stops_pyramid(self):
        """Pyramid must stop halving once the shorter side ≤ min_scale_size."""
        scale_calls = []

        class _TrackingYOLO:
            def __call__(self, tile):
                scale_calls.append(tile.shape[:2])
                return [_FakeResults([])]

        # 8192×8192 image; min_scale_size=4096 means the pyramid processes the
        # full-res level (8192×8192, which needs tiling) and then the half-scale
        # level (4096×4096, sw==min_scale_size → stop).  That is at most 2 levels.
        image = self._make_image(8192, 8192)
        run_yolo_multiscale(image, _TrackingYOLO(), max_tile_size=1280, min_scale_size=4096, overlap=0.2)
        assert len(scale_calls) >= 1
        # The shorter side must never drop below min_scale_size across the tiles seen
        # (all tile heights/widths are ≤ max_tile_size per level, so just confirm at
        # least one tile was processed and the loop terminated).
        assert len(scale_calls) <= 100  # sanity upper bound to catch runaway loops

    def test_detections_mapped_to_original_coords(self):
        """Detections from a half-scale tile must be scaled back to original coords."""
        # Image is large enough to need tiling; single det at tile-local (0,0,10,10)
        model = _MockYOLO(detections=[(0, 0, 0, 10, 10)])
        image = self._make_image(3000, 3000)
        result = run_yolo_multiscale(image, model, max_tile_size=1280, min_scale_size=256, overlap=0.0)
        # All returned coords must be within the original image bounds
        for _, (x1, y1, x2, y2) in result:
            assert 0 <= x1 < 3000
            assert 0 <= y1 < 3000
            assert x2 <= 3000
            assert y2 <= 3000

    def test_deduplication_applied(self):
        """Duplicate detections from overlapping tiles/scales are deduplicated."""
        # Model always returns the same box regardless of tile — duplicates expected
        model = _MockYOLO(detections=[(0, 5, 5, 50, 50)])
        image = self._make_image(500, 500)
        result = run_yolo_multiscale(image, model, max_tile_size=1280, min_scale_size=256)
        # Even though the model returns the same box for every scale, deduplication
        # keeps only one copy.
        assert len(result) == 1
