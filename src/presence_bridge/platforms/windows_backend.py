from __future__ import annotations

from pathlib import Path

from .base import ActiveWindow, MediaMetadata, PlatformBackend
from ..models import CropRect


class WindowsPlatformBackend(PlatformBackend):
    """Windows implementation boundary.

    The Linux version is validated first. Do not fork shared GUI/config logic when
    filling this in.
    """

    def active_window(self) -> ActiveWindow:
        return ActiveWindow()

    def media_metadata(self) -> MediaMetadata:
        return MediaMetadata()

    def capture_fullscreen(self, destination: Path) -> Path:
        raise RuntimeError("Windows capture is the next platform milestone")

    def capture_crop(self, crop: CropRect, destination: Path) -> Path:
        raise RuntimeError("Windows capture is the next platform milestone")

    def diagnostics(self) -> list[tuple[str, bool, str]]:
        return [
            ("Windows backend", True, "shared architecture loaded"),
            ("Foreground-window metadata", False, "not implemented yet"),
            ("Windows Graphics Capture", False, "not implemented yet"),
        ]
