"""Stage 4A company and financial-aspect contracts."""

from .contracts import *
from .runtime import (
    Stage4APipeline,
    Stage4AResult,
    adapt_legacy_comparison,
    adapt_legacy_competitor,
    extract_aspect_mentions,
)
from .service import Stage4AService

__all__ = [
    "Stage4APipeline",
    "Stage4AResult",
    "extract_aspect_mentions",
    "adapt_legacy_comparison",
    "adapt_legacy_competitor",
    "Stage4AService",
]
