from __future__ import annotations

import asyncio
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image
from dbus_next import Message, MessageType
from dbus_next.aio import MessageBus

from .base import ActiveWindow, MediaMetadata, PlatformBackend
from .kwin_windows import list_kwin_taskbar_processes
from ..models import CropRect


def _variant_value(mapping, key, default=""):
    value = mapping.get(key)
    if value is None:
        return default
    return getattr(value, "value", default)


async def _query_mpris() -> MediaMetadata:
    bus = await MessageBus().connect()
    try:
        reply = await bus.call(
            Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="ListNames",
            )
        )
        if reply.message_type == MessageType.ERROR:
            return MediaMetadata()

        names = [name for name in reply.body[0] if name.startswith("org.mpris.MediaPlayer2.")]
        fallback = None

        for name in names:
            props_reply = await bus.call(
                Message(
                    destination=name,
                    path="/org/mpris/MediaPlayer2",
                    interface="org.freedesktop.DBus.Properties",
                    member="GetAll",
                    signature="s",
                    body=["org.mpris.MediaPlayer2.Player"],
                )
            )
            if props_reply.message_type == MessageType.ERROR:
                continue

            props = props_reply.body[0]
            status = str(_variant_value(props, "PlaybackStatus", ""))
            metadata_variant = props.get("Metadata")
            metadata = getattr(metadata_variant, "value", {}) if metadata_variant else {}

            artist_value = _variant_value(metadata, "xesam:artist", [])
            if isinstance(artist_value, (list, tuple)):
                artist = ", ".join(str(x) for x in artist_value)
            else:
                artist = str(artist_value or "")

            item = MediaMetadata(
                playing=status.casefold() == "playing",
                title=str(_variant_value(metadata, "xesam:title", "") or ""),
                artist=artist,
                album=str(_variant_value(metadata, "xesam:album", "") or ""),
                art_url=str(_variant_value(metadata, "mpris:artUrl", "") or ""),
                player=name.removeprefix("org.mpris.MediaPlayer2."),
            )
            if item.playing:
                return item
            if fallback is None and (item.title or item.artist):
                fallback = item

        return fallback or MediaMetadata()
    finally:
        bus.disconnect()


@lru_cache(maxsize=256)
def _resolve_linux_app_icon(process_name: str, process_exe: str) -> Path | None:
    """Best-effort .desktop/icon-theme resolver for a running process."""
    executable = Path(process_exe).name.casefold() if process_exe else ""
    pname = Path(process_name).name.casefold()

    desktop_roots = [
        Path.home() / ".local/share/applications",
        Path.home() / ".local/share/flatpak/exports/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        Path("/usr/local/share/applications"),
        Path("/usr/share/applications"),
    ]

    icon_name = ""
    for root in desktop_roots:
        if not root.exists():
            continue
        try:
            desktop_files = root.glob("*.desktop")
        except OSError:
            continue
        for entry in desktop_files:
            try:
                content = entry.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            exec_match = re.search(r"^Exec=(.+)$", content, re.M)
            name_match = re.search(r"^Name=(.+)$", content, re.M)
            exec_line = exec_match.group(1).casefold() if exec_match else ""
            display_name = name_match.group(1).casefold() if name_match else ""
            if not (
                (executable and executable in exec_line)
                or (pname and pname in exec_line)
                or (pname and pname in display_name)
            ):
                continue
            icon_match = re.search(r"^Icon=(.+)$", content, re.M)
            if icon_match:
                icon_name = icon_match.group(1).strip()
                break
        if icon_name:
            break

    if not icon_name:
        icon_name = executable or pname

    absolute = Path(icon_name).expanduser()
    if absolute.is_absolute() and absolute.exists() and absolute.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        return absolute

    icon_roots = [
        Path.home() / ".local/share/icons",
        Path.home() / ".icons",
        Path.home() / ".local/share/flatpak/exports/share/icons",
        Path("/var/lib/flatpak/exports/share/icons"),
        Path("/usr/share/icons"),
        Path("/usr/share/pixmaps"),
    ]
    names = {icon_name, icon_name.casefold(), executable, pname}
    names.discard("")

    candidates: list[Path] = []
    for root in icon_roots:
        if not root.exists():
            continue
        for name in names:
            for ext in (".png", ".webp", ".jpg", ".jpeg"):
                try:
                    candidates.extend(root.glob(f"**/{name}{ext}"))
                except OSError:
                    pass

    if not candidates:
        return None

    def score(path: Path):
        # Prefer larger hicolor sizes, then shorter/more canonical paths.
        size_score = 0
        for part in path.parts:
            m = re.fullmatch(r"(\d+)x(\d+)", part)
            if m:
                size_score = max(size_score, int(m.group(1)) * int(m.group(2)))
        return (size_score, -len(str(path)))

    return max(candidates, key=score)


class LinuxPlatformBackend(PlatformBackend):
    def active_window(self) -> ActiveWindow:
        # Deliberately isolated here. KDE Wayland active-window metadata is a later
        # backend milestone; do not contaminate the GUI with X11-only tricks.
        return ActiveWindow()

    def media_metadata(self) -> MediaMetadata:
        try:
            return asyncio.run(_query_mpris())
        except Exception:
            return MediaMetadata()


    def application_icon(self, process) -> Path | None:
        return _resolve_linux_app_icon(process.name, process.exe)

    def taskbar_processes(self):
        return list_kwin_taskbar_processes()

    def capture_fullscreen(self, destination: Path) -> Path:
        spectacle = shutil.which("spectacle")
        if not spectacle:
            raise RuntimeError("KDE Spectacle was not found in PATH")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination.unlink()
        cp = subprocess.run(
            [
                spectacle,
                "--fullscreen",
                "--background",
                "--nonotify",
                "--output",
                str(destination),
            ],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        if cp.returncode != 0 or not destination.exists():
            message = (cp.stderr or cp.stdout or "unknown Spectacle failure").strip()
            raise RuntimeError(f"Spectacle capture failed: {message}")
        return destination

    def capture_crop(self, crop: CropRect, destination: Path) -> Path:
        if not crop.valid:
            raise RuntimeError("No valid crop rectangle has been selected")
        full = destination.with_name(destination.stem + "-full.png")
        self.capture_fullscreen(full)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(full) as image:
            left = max(0, crop.x)
            top = max(0, crop.y)
            right = min(image.width, crop.x + crop.width)
            bottom = min(image.height, crop.y + crop.height)
            if right <= left or bottom <= top:
                raise RuntimeError("Saved crop lies outside the current screenshot")
            piece = image.crop((left, top, right, bottom))
            piece.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
            piece.save(destination, "WEBP", quality=82, method=5)
        try:
            full.unlink()
        except OSError:
            pass
        return destination

    def diagnostics(self) -> list[tuple[str, bool, str]]:
        return [
            (
                "Wayland session",
                bool(os.environ.get("WAYLAND_DISPLAY")),
                os.environ.get("WAYLAND_DISPLAY") or "not detected",
            ),
            (
                "KDE Spectacle",
                shutil.which("spectacle") is not None,
                shutil.which("spectacle") or "missing",
            ),
            (
                "cloudflared",
                shutil.which("cloudflared") is not None,
                shutil.which("cloudflared") or "missing (only required for live crop relay)",
            ),
            (
                "Session D-Bus",
                bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS")),
                "available" if os.environ.get("DBUS_SESSION_BUS_ADDRESS") else "not detected",
            ),
        ]
