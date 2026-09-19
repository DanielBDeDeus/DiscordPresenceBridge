from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..models import CropRect


@dataclass
class ActiveWindow:
    title: str = ""
    app_id: str = ""


@dataclass
class MediaMetadata:
    playing: bool = False
    title: str = ""
    artist: str = ""
    album: str = ""
    art_url: str = ""
    player: str = ""


class PlatformBackend:
    def active_window(self) -> ActiveWindow:
        return ActiveWindow()

    def media_metadata(self) -> MediaMetadata:
        return MediaMetadata()

    def application_icon(self, process) -> Path | None:
        return None

    def taskbar_processes(self):
        return []

    def capture_fullscreen(self, destination: Path) -> Path:
        raise RuntimeError("Screenshot capture is not implemented on this platform")

    def capture_crop(self, crop: CropRect, destination: Path) -> Path:
        raise RuntimeError("Crop capture is not implemented on this platform")

    def diagnostics(self) -> list[tuple[str, bool, str]]:
        return []


class GenericPlatformBackend(PlatformBackend):
    pass
