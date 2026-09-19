from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import shlex
import sys

import psutil


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str
    exe: str

    @property
    def display(self) -> str:
        return f"{self.name}  [PID {self.pid}]"


_FIELD_CODE = re.compile(r"^%[fFuUdDnNickvm]$")
_WRAPPER_COMMANDS = {
    "env",
    "flatpak",
    "run",
    "sh",
    "bash",
    "zsh",
    "fish",
    "python",
    "python3",
}


def list_processes() -> list[ProcessInfo]:
    result: list[ProcessInfo] = []
    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = proc.info.get("name") or ""
            if not name:
                continue
            result.append(
                ProcessInfo(
                    pid=int(proc.info["pid"]),
                    name=name,
                    exe=proc.info.get("exe") or "",
                )
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    result.sort(key=lambda p: (p.name.casefold(), p.pid))
    return result


def _desktop_entry_value(content: str, key: str) -> str:
    in_desktop_entry = False
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_desktop_entry = line == "[Desktop Entry]"
            continue
        if not in_desktop_entry or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key == key:
            return value.strip()
    return ""


def desktop_entry_aliases(content: str, stem: str) -> set[str]:
    """Return process/app identifiers that a visible desktop launcher may use."""
    if _desktop_entry_value(content, "Type").casefold() not in ("", "application"):
        return set()
    if _desktop_entry_value(content, "Hidden").casefold() == "true":
        return set()
    if _desktop_entry_value(content, "NoDisplay").casefold() == "true":
        return set()

    aliases: set[str] = set()

    def add(value: str) -> None:
        value = value.strip().casefold()
        if not value:
            return
        aliases.add(value)
        aliases.add(Path(value).name)

    add(stem)
    if "." in stem:
        add(stem.rsplit(".", 1)[-1])

    add(_desktop_entry_value(content, "StartupWMClass"))
    add(_desktop_entry_value(content, "TryExec"))

    exec_line = _desktop_entry_value(content, "Exec")
    if exec_line:
        try:
            tokens = shlex.split(exec_line)
        except ValueError:
            tokens = exec_line.split()

        for token in tokens:
            if not token or _FIELD_CODE.match(token):
                continue
            if token.startswith("-"):
                continue
            clean = token.strip("'\"")
            base = Path(clean).name.casefold()
            if base in _WRAPPER_COMMANDS:
                continue
            if "=" in clean and "/" not in clean:
                # Environment assignment such as FOO=bar.
                continue
            add(clean)

        # Flatpak desktop entries usually contain an application ID whose last
        # component is close to the visible process/window class.
        flatpak_match = re.search(r"\b(?:run\s+)?([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,})\b", exec_line)
        if flatpak_match:
            app_id = flatpak_match.group(1)
            add(app_id)
            add(app_id.rsplit(".", 1)[-1])

    return {alias for alias in aliases if len(alias) >= 2}


def _linux_desktop_aliases() -> set[str]:
    roots: list[Path] = [
        Path.home() / ".local/share/applications",
        Path.home() / ".local/share/flatpak/exports/share/applications",
        Path("/var/lib/flatpak/exports/share/applications"),
    ]

    for value in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":"):
        if value:
            roots.append(Path(value) / "applications")

    aliases: set[str] = set()
    seen_paths: set[Path] = set()
    for root in roots:
        if root in seen_paths or not root.exists():
            continue
        seen_paths.add(root)
        try:
            entries = root.glob("*.desktop")
        except OSError:
            continue
        for entry in entries:
            try:
                content = entry.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            aliases.update(desktop_entry_aliases(content, entry.stem))
    return aliases


def _process_aliases(proc: ProcessInfo) -> set[str]:
    values = {proc.name.casefold()}
    if proc.exe:
        values.add(Path(proc.exe).name.casefold())
    return {value for value in values if value}


def _looks_like_visible_app(proc: ProcessInfo, desktop_aliases: set[str]) -> bool:
    candidates = _process_aliases(proc)
    if candidates & desktop_aliases:
        return True

    # Some launchers use a descriptive desktop ID while the process adds a
    # common suffix such as "-bin".
    for candidate in candidates:
        trimmed = candidate.removesuffix("-bin").removesuffix(".bin")
        if trimmed in desktop_aliases:
            return True
    return False


def list_user_app_processes() -> list[ProcessInfo]:
    """Return a short, user-facing process list for the app picker.

    On Linux this intentionally prefers running processes that can be matched to
    visible .desktop launchers. It is not a kernel-process browser: the GUI has a
    separate "show background processes" switch for that.
    """
    processes = list_processes()
    if not sys.platform.startswith("linux"):
        return processes

    desktop_aliases = _linux_desktop_aliases()
    if not desktop_aliases:
        return processes

    result: list[ProcessInfo] = []
    seen: set[tuple[str, str]] = set()
    for proc in processes:
        if not _looks_like_visible_app(proc, desktop_aliases):
            continue
        key = (proc.name.casefold(), proc.exe.casefold())
        if key in seen:
            continue
        seen.add(key)
        result.append(proc)
    return result


def find_matching_process(pattern: str) -> ProcessInfo | None:
    needle = pattern.strip().casefold()
    if not needle:
        return None
    for proc in list_processes():
        if needle in f"{proc.name}\n{proc.exe}".casefold():
            return proc
    return None
