from __future__ import annotations

import sys

from .base import PlatformBackend


def get_platform_backend() -> PlatformBackend:
    if sys.platform.startswith("linux"):
        from .linux_backend import LinuxPlatformBackend
        return LinuxPlatformBackend()
    if sys.platform == "win32":
        from .windows_backend import WindowsPlatformBackend
        return WindowsPlatformBackend()
    from .base import GenericPlatformBackend
    return GenericPlatformBackend()
