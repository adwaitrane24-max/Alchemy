"""Fast Request Detector — detects trivial prompts to bypass the full routing pipeline."""

from __future__ import annotations

from backend.app.modules.fast_detector.detector import FastRequestDetector

__all__ = ["FastRequestDetector"]
