from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
import uuid
from typing import Callable

import psutil
from dbus_next import Message, MessageType
from dbus_next.aio import MessageBus

from ..processes import ProcessInfo


_BRIDGE_PATH = "/io/github/DanielBDeDeus/DiscordPresenceBridge/KWinBridge"
_BRIDGE_INTERFACE = "io.github.DanielBDeDeus.DiscordPresenceBridge.KWinBridge"


@dataclass(frozen=True)
class KWinTaskbarWindow:
    pid: int
    caption: str = ""
    resource_class: str = ""
    resource_name: str = ""
    desktop_file_name: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "KWinTaskbarWindow":
        return cls(
            pid=int(data.get("pid") or 0),
            caption=str(data.get("caption") or ""),
            resource_class=str(data.get("resourceClass") or ""),
            resource_name=str(data.get("resourceName") or ""),
            desktop_file_name=str(data.get("desktopFileName") or ""),
        )


def _clean_app_name(value: str) -> str:
    value = value.strip()
    if not value:
        return ""

    base = Path(value).name
    if base.endswith(".desktop"):
        base = base[:-8]

    lowered = base.casefold()
    if lowered.startswith("steam_app_"):
        return ""

    # Namespaced desktop IDs such as com.discordapp.Discord are much nicer
    # when displayed using their final component.
    if base.count(".") >= 2 and " " not in base:
        base = base.rsplit(".", 1)[-1]

    for suffix in (".x86_64", ".x86", ".exe", ".bin"):
        if base.casefold().endswith(suffix):
            base = base[: -len(suffix)]
            break

    base = base.replace("_", " ").replace("-", " ").strip()
    if not base:
        return ""

    return " ".join(piece.capitalize() if piece.islower() else piece for piece in base.split())


def _display_name(window: KWinTaskbarWindow, process_name: str) -> str:
    desktop_name = _clean_app_name(window.desktop_file_name)
    if desktop_name:
        return desktop_name

    resource_name = _clean_app_name(window.resource_class)
    generic = {
        "steam",
        "wine",
        "xwayland",
        "gamescope",
        "python",
        "python3",
    }
    if resource_name and resource_name.casefold() not in generic:
        return resource_name

    caption = window.caption.strip()
    if caption:
        # Captions are especially useful for Steam/Proton games, where there
        # may be no desktop file that maps to the real game process.
        return caption[:100]

    return _clean_app_name(process_name) or process_name


def _records_to_processes(
    records: list[KWinTaskbarWindow],
    process_lookup: Callable[[int], object] = psutil.Process,
) -> list[ProcessInfo]:
    result: list[ProcessInfo] = []
    seen: set[tuple[str, str]] = set()

    for window in records:
        if window.pid <= 0:
            continue

        try:
            proc = process_lookup(window.pid)
            name = str(proc.name() or "")
            exe = str(proc.exe() or "")
        except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError, PermissionError):
            continue

        if not name:
            continue

        key = (name.casefold(), exe.casefold())
        if key in seen:
            continue
        seen.add(key)

        result.append(
            ProcessInfo(
                pid=window.pid,
                name=name,
                exe=exe,
                display_name=_display_name(window, name),
                window_title=window.caption,
                app_id=window.desktop_file_name or window.resource_class,
            )
        )

    result.sort(key=lambda item: item.display.casefold())
    return result


def _kwin_script(destination: str) -> str:
    destination_json = json.dumps(destination)
    path_json = json.dumps(_BRIDGE_PATH)
    interface_json = json.dumps(_BRIDGE_INTERFACE)

    return f"""
try {{
    const windows = workspace.windowList();
    const result = [];

    for (let i = 0; i < windows.length; i++) {{
        const w = windows[i];

        // This mirrors the user's intent much more closely than guessing from
        // installed .desktop files: if KWin says the window belongs on the
        // taskbar, it belongs in our default picker.
        if (!w.managed || w.deleted || w.skipTaskbar || w.desktopWindow || w.dock) {{
            continue;
        }}

        result.push({{
            pid: w.pid,
            caption: w.caption,
            resourceClass: w.resourceClass,
            resourceName: w.resourceName,
            desktopFileName: w.desktopFileName
        }});
    }}

    callDBus(
        {destination_json},
        {path_json},
        {interface_json},
        "result",
        JSON.stringify(result)
    );
}} catch (e) {{
    callDBus(
        {destination_json},
        {path_json},
        {interface_json},
        "error",
        e.toString()
    );
}}
"""


def _dbus_error(reply: Message, action: str) -> RuntimeError:
    detail = ""
    if reply.body:
        detail = ": " + " ".join(str(item) for item in reply.body)
    return RuntimeError(f"KWin {action} failed{detail}")


async def _query_taskbar_windows() -> list[KWinTaskbarWindow]:
    bus = await MessageBus().connect()
    loop = asyncio.get_running_loop()
    response: asyncio.Future[str] = loop.create_future()

    def handler(message: Message):
        if (
            message.message_type == MessageType.METHOD_CALL
            and message.path == _BRIDGE_PATH
            and message.interface == _BRIDGE_INTERFACE
        ):
            if message.member == "result":
                if not response.done():
                    response.set_result(str(message.body[0] if message.body else "[]"))
            elif message.member == "error":
                if not response.done():
                    response.set_exception(
                        RuntimeError(str(message.body[0] if message.body else "Unknown KWin error"))
                    )
            return Message.new_method_return(message)
        return None

    bus.add_message_handler(handler)

    # dbus-next documents that custom message handlers should have an explicit
    # match rule. Calls are still addressed to this connection's unique name.
    match_reply = await bus.call(
        Message(
            destination="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            interface="org.freedesktop.DBus",
            member="AddMatch",
            signature="s",
            body=[
                "type='method_call',"
                f"interface='{_BRIDGE_INTERFACE}',"
                f"path='{_BRIDGE_PATH}'"
            ],
        )
    )
    if match_reply.message_type == MessageType.ERROR:
        bus.disconnect()
        raise _dbus_error(match_reply, "D-Bus match setup")

    script_name = f"presencebridge-taskbar-{uuid.uuid4().hex}"
    script_file = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="presencebridge-kwin-",
        suffix=".js",
        delete=False,
    )
    script_path = script_file.name
    script_id: int | None = None

    try:
        script_file.write(_kwin_script(bus.unique_name))
        script_file.close()

        load_reply = await bus.call(
            Message(
                destination="org.kde.KWin",
                path="/Scripting",
                interface="org.kde.kwin.Scripting",
                member="loadScript",
                signature="ss",
                body=[script_path, script_name],
            )
        )
        if load_reply.message_type == MessageType.ERROR:
            raise _dbus_error(load_reply, "script load")

        script_id = int(load_reply.body[0])
        if script_id < 0:
            raise RuntimeError("KWin refused to load the temporary taskbar query script")

        run_reply = await bus.call(
            Message(
                destination="org.kde.KWin",
                path=f"/Scripting/Script{script_id}",
                interface="org.kde.kwin.Script",
                member="run",
            )
        )
        if run_reply.message_type == MessageType.ERROR:
            raise _dbus_error(run_reply, "script run")

        payload = await asyncio.wait_for(response, timeout=4.0)
        decoded = json.loads(payload)
        if not isinstance(decoded, list):
            raise RuntimeError("KWin returned an unexpected taskbar-window payload")

        return [
            KWinTaskbarWindow.from_dict(item)
            for item in decoded
            if isinstance(item, dict)
        ]
    finally:
        if script_id is not None and script_id >= 0:
            try:
                await bus.call(
                    Message(
                        destination="org.kde.KWin",
                        path=f"/Scripting/Script{script_id}",
                        interface="org.kde.kwin.Script",
                        member="stop",
                    )
                )
            except Exception:
                pass

            try:
                await bus.call(
                    Message(
                        destination="org.kde.KWin",
                        path="/Scripting",
                        interface="org.kde.kwin.Scripting",
                        member="unloadScript",
                        signature="s",
                        body=[script_name],
                    )
                )
            except Exception:
                pass

        try:
            Path(script_path).unlink(missing_ok=True)
        except OSError:
            pass
        bus.disconnect()


def list_kwin_taskbar_processes() -> list[ProcessInfo]:
    """Return processes backing the windows KWin says belong on the taskbar."""
    return _records_to_processes(asyncio.run(_query_taskbar_windows()))
