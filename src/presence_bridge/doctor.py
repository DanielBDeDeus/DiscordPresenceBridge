from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

from .config import config_path, load_config
from .discord.ipc import find_linux_socket, linux_socket_candidates
from .platforms import get_platform_backend


def run_doctor() -> int:
    config = load_config()
    checks: list[tuple[str, bool, str]] = []

    checks.append(("Config file", config_path().exists(), str(config_path())))
    checks.append(
        (
            "Discord Application ID",
            bool(config.discord_application_id),
            config.discord_application_id or "not configured yet",
        )
    )

    platform = get_platform_backend()
    checks.extend(platform.diagnostics())

    if os.name == "posix":
        socket_path = find_linux_socket()
        checks.append(
            (
                "Discord IPC socket",
                socket_path is not None,
                str(socket_path) if socket_path else "not found",
            )
        )
        service = subprocess.run(
            ["systemctl", "--user", "is-enabled", "discord-presence-bridge.service"],
            text=True,
            capture_output=True,
            check=False,
        )
        checks.append(
            (
                "systemd user service",
                service.returncode == 0,
                (service.stdout or service.stderr).strip() or "not installed",
            )
        )

    width = max(len(name) for name, _, _ in checks)
    failed = 0
    for name, ok, detail in checks:
        mark = "OK " if ok else "!! "
        print(f"{mark}{name:<{width}}  {detail}")
        if not ok:
            failed += 1

    if os.name == "posix" and find_linux_socket() is None:
        print("\nChecked Discord socket candidates including:")
        for item in linux_socket_candidates()[:6]:
            print(f"  {item}")
        print("  ... plus Flatpak Discord/Vesktop runtime paths")

    print(f"\n{len(checks) - failed}/{len(checks)} checks currently pass.")
    return 0
