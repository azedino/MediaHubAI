"""Backward-compatible facade for the modular shorts pipeline."""

from __future__ import annotations

from .renderer import FILTER_CHAINS
from .short_pipeline import ShortPipeline


class ShortCreationService(ShortPipeline):
    """Public service kept stable for the API and Streamlit integration."""


__all__ = ["FILTER_CHAINS", "ShortCreationService"]
