from pathlib import Path

import pytest

from core.errors import InvalidMediaError
from core.models import ExportPreset, ShortsRequest


def test_export_presets_have_even_social_dimensions() -> None:
    for preset in ExportPreset:
        width, height = preset.dimensions
        assert width % 2 == 0
        assert height % 2 == 0
        assert width >= 1080


def test_request_rejects_missing_source(tmp_path: Path) -> None:
    request = ShortsRequest(source=tmp_path / "missing.mp4", output_dir=tmp_path)
    with pytest.raises(InvalidMediaError):
        request.validate()
