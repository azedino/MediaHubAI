import numpy as np
import pytest

from services.geometry import BoundingBox
from services.tracker import OpenCVBoxTracker


def test_opencv_box_tracker_initialize_uses_int_bounding_box() -> None:
    pytest.importorskip("cv2")
    import cv2

    tracker = OpenCVBoxTracker(cv2)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    box = BoundingBox(100, 50, 120, 150)

    assert tracker.initialize(frame, box)
    assert tracker._tracker is not None
