from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import struct
import sys
import uuid

from .base import DiscordBackend, PresencePayload


OP_HANDSHAKE = 0
OP_FRAME = 1
TYPE_MAP = {
    "playing": 0,
    "streaming": 1,
    "listening": 2,
    "watching": 3,
    "competing": 5,
}


def linux_socket_candidates() -> list[Path]:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    roots = [
        runtime,
        Path("/tmp"),
        runtime / "app/com.discordapp.Discord",
        runtime / "app/com.discordapp.DiscordCanary",
        runtime / "app/dev.vencord.Vesktop",
        runtime / "app/com.vesktop.Vesktop",
    ]
    candidates: list[Path] = []
    for root in roots:
        for i in range(10):
            candidates.append(root / f"discord-ipc-{i}")
    return candidates


def find_linux_socket() -> Path | None:
    for path in linux_socket_candidates():
        try:
            if path.exists():
                return path
        except OSError:
            pass
    return None


class LocalDiscordIPC(DiscordBackend):
    def __init__(self) -> None:
        self.sock: socket.socket | None = None
        self.application_id = ""

    def _send(self, opcode: int, payload: dict) -> None:
        if not self.sock:
            raise RuntimeError("Discord IPC is not connected")
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.sock.sendall(struct.pack("<II", opcode, len(raw)) + raw)

    def _recv(self) -> dict:
        if not self.sock:
            raise RuntimeError("Discord IPC is not connected")

        def exact(count: int) -> bytes:
            buf = bytearray()
            while len(buf) < count:
                chunk = self.sock.recv(count - len(buf))
                if not chunk:
                    raise RuntimeError("Discord IPC closed the connection")
                buf.extend(chunk)
            return bytes(buf)

        header = exact(8)
        _opcode, length = struct.unpack("<II", header)
        payload = exact(length)
        return json.loads(payload.decode("utf-8"))

    def connect(self, application_id: str) -> None:
        application_id = application_id.strip()
        if not application_id:
            raise ValueError("Discord Application ID is empty")
        if self.sock and self.application_id == application_id:
            return
        self.close()

        if sys.platform.startswith("linux"):
            path = find_linux_socket()
            if not path:
                raise RuntimeError(
                    "No Discord IPC socket found. Start Discord/Vesktop and run "
                    "`presence-bridge doctor`."
                )
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(3.0)
            sock.connect(str(path))
        else:
            raise RuntimeError(
                "The current raw IPC transport is implemented for Linux first; "
                "Windows transport is a follow-up milestone."
            )

        self.sock = sock
        self.application_id = application_id
        self._send(OP_HANDSHAKE, {"v": 1, "client_id": application_id})
        reply = self._recv()
        if reply.get("evt") not in ("READY", None) and reply.get("cmd") != "DISPATCH":
            raise RuntimeError(f"Unexpected Discord handshake response: {reply}")

    def publish(self, payload: PresencePayload) -> None:
        if not self.sock:
            raise RuntimeError("Discord IPC is not connected")

        activity: dict = {
            "type": TYPE_MAP.get(payload.activity_type, 0),
        }
        if payload.name:
            activity["name"] = payload.name[:128]
        if payload.details:
            activity["details"] = payload.details[:128]
        if payload.state:
            activity["state"] = payload.state[:128]

        assets = {}
        if payload.large_image:
            assets["large_image"] = payload.large_image
        if payload.large_text:
            assets["large_text"] = payload.large_text[:128]
        if payload.small_image:
            assets["small_image"] = payload.small_image
        if payload.small_text:
            assets["small_text"] = payload.small_text[:128]
        if assets:
            activity["assets"] = assets

        self._send(
            OP_FRAME,
            {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": activity},
                "nonce": str(uuid.uuid4()),
            },
        )
        try:
            self._recv()
        except socket.timeout:
            pass

    def clear(self) -> None:
        if not self.sock:
            return
        self._send(
            OP_FRAME,
            {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": None},
                "nonce": str(uuid.uuid4()),
            },
        )
        try:
            self._recv()
        except socket.timeout:
            pass

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None
        self.application_id = ""
