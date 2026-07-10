"""Small geometry primitives used by the shorts rendering pipeline."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @property
    def center(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    @property
    def aspect_ratio(self) -> float:
        return self.width / max(1, self.height)

    def clamp(self, frame_width: int, frame_height: int) -> BoundingBox:
        width = min(max(2, self.width), max(2, frame_width))
        height = min(max(2, self.height), max(2, frame_height))
        x = min(max(0, self.x), max(0, frame_width - width))
        y = min(max(0, self.y), max(0, frame_height - height))
        return BoundingBox(int(x), int(y), int(width), int(height)).even()

    def even(self) -> BoundingBox:
        width = max(2, self.width // 2 * 2)
        height = max(2, self.height // 2 * 2)
        x = max(0, self.x // 2 * 2)
        y = max(0, self.y // 2 * 2)
        return BoundingBox(x, y, width, height)

    def expand(self, scale_x: float, scale_y: float, frame_width: int, frame_height: int) -> BoundingBox:
        center_x, center_y = self.center
        width = round(self.width * scale_x)
        height = round(self.height * scale_y)
        return BoundingBox(
            round(center_x - width / 2),
            round(center_y - height / 2),
            width,
            height,
        ).clamp(frame_width, frame_height)

    def iou(self, other: BoundingBox) -> float:
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.x + self.width, other.x + other.width)
        bottom = min(self.y + self.height, other.y + other.height)
        intersection = max(0, right - left) * max(0, bottom - top)
        union = self.area + other.area - intersection
        return intersection / union if union else 0.0

    def distance_to(self, other: BoundingBox) -> float:
        sx, sy = self.center
        ox, oy = other.center
        return ((sx - ox) ** 2 + (sy - oy) ** 2) ** 0.5

    def as_tuple(self) -> tuple[int, int, int, int]:
        return self.x, self.y, self.width, self.height

    @classmethod
    def from_tuple(cls, value: tuple[int, int, int, int]) -> BoundingBox:
        return cls(*value)
