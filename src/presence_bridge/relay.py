from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import queue
import re
import shutil
import subprocess
import threading
import time


class _AssetStore:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.assets: dict[str, tuple[bytes, str]] = {}

    def put(self, data: bytes, mime: str) -> str:
        digest = hashlib.sha256(data).hexdigest()[:24]
        with self.lock:
            self.assets[digest] = (data, mime)
            if len(self.assets) > 4:
                for old in list(self.assets)[:-4]:
                    self.assets.pop(old, None)
        return digest

    def get(self, digest: str):
        with self.lock:
            return self.assets.get(digest)


class LiveAssetRelay:
    """Serve generated images locally and optionally expose them through cloudflared."""

    def __init__(self) -> None:
        self.store = _AssetStore()
        self.server = None
        self.server_thread = None
        self.tunnel = None
        self.public_base = ""

    def start(self) -> str:
        if self.public_base:
            return self.public_base
        cloudflared = shutil.which("cloudflared")
        if not cloudflared:
            raise RuntimeError(
                "cloudflared is missing. Re-run scripts/install-linux.sh or install it "
                "with `brew install cloudflared`."
            )

        store = self.store

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                match = re.fullmatch(r"/asset/([0-9a-f]{24})\.(webp|png|jpg)", self.path.split("?")[0])
                if not match:
                    self.send_response(404)
                    self.end_headers()
                    return
                item = store.get(match.group(1))
                if not item:
                    self.send_response(404)
                    self.end_headers()
                    return
                data, mime = item
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "public, max-age=30")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = self.server.server_address[1]
        self.server_thread = threading.Thread(
            target=self.server.serve_forever,
            name="presence-asset-http",
            daemon=True,
        )
        self.server_thread.start()

        self.tunnel = subprocess.Popen(
            [
                cloudflared,
                "tunnel",
                "--no-autoupdate",
                "--url",
                f"http://127.0.0.1:{port}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        found: queue.Queue[str] = queue.Queue()

        def watch():
            assert self.tunnel and self.tunnel.stdout
            pattern = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")
            for line in self.tunnel.stdout:
                match = pattern.search(line)
                if match:
                    try:
                        found.put_nowait(match.group(0))
                    except queue.Full:
                        pass
                    break

        threading.Thread(target=watch, daemon=True).start()

        try:
            self.public_base = found.get(timeout=20)
        except queue.Empty as exc:
            self.stop()
            raise RuntimeError("cloudflared did not provide a Quick Tunnel URL") from exc

        return self.public_base

    def publish_file(self, path: Path) -> str:
        base = self.start()
        data = path.read_bytes()
        suffix = path.suffix.lower()
        mime = {
            ".webp": "image/webp",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }.get(suffix, "application/octet-stream")
        digest = self.store.put(data, mime)
        ext = "jpg" if suffix == ".jpeg" else suffix.lstrip(".")
        return f"{base}/asset/{digest}.{ext}"

    def stop(self) -> None:
        self.public_base = ""
        if self.tunnel:
            try:
                self.tunnel.terminate()
            except OSError:
                pass
            self.tunnel = None
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except OSError:
                pass
            self.server = None
