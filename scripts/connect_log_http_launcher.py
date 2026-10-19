# /// script
# requires-python = ">=3.11"
# ///
# How to run: python scripts/connect_log_http_launcher.py

from __future__ import annotations

import argparse
import socket
import subprocess
import time
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit


LOOPBACK_HOST: Final = "127.0.0.1"
DEFAULT_PORT: Final = 8765
APP_URL: Final = "http://localhost:8501"
STARTUP_TIMEOUT_SECONDS: Final = 75.0


@dataclass(frozen=True, slots=True)
class LauncherConfig:
    app_root: Path
    port: int
    dry_run: bool


class LauncherServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, config: LauncherConfig) -> None:
        self.config = config
        super().__init__((LOOPBACK_HOST, config.port), LauncherRequestHandler)


class LauncherRequestHandler(BaseHTTPRequestHandler):
    server: LauncherServer

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        match path:
            case "/health":
                self._send_text(HTTPStatus.OK, "ok")
            case "/" | "/open":
                self._open_app()
            case _:
                self._send_text(HTTPStatus.NOT_FOUND, "not found")

    def log_message(self, format: str, *args: str | int) -> None:
        return

    def _open_app(self) -> None:
        config = self.server.config
        if not config.dry_run:
            try:
                ensure_app_is_ready(config.app_root)
            except (OSError, subprocess.SubprocessError) as error:
                self._send_text(HTTPStatus.SERVICE_UNAVAILABLE, f"app start failed: {error}")
                return

        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", APP_URL)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send_text(self, status: HTTPStatus, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)


def port_is_open() -> bool:
    try:
        with socket.create_connection(("localhost", 8501), timeout=0.5):
            return True
    except OSError:
        return False


def ensure_app_is_ready(app_root: Path) -> None:
    if not port_is_open():
        run_app_path = app_root / "run_app.ps1"
        powershell_path = Path("C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
        subprocess.Popen(
            [
                str(powershell_path),
                "-NoProfile",
                "-WindowStyle",
                "Hidden",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(run_app_path),
                "-NoPrompt",
                "-SkipBrowser",
            ],
            cwd=app_root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if port_is_open():
            return
        time.sleep(0.25)
    raise TimeoutError("Streamlit did not become ready within 75 seconds")


def parse_args() -> LauncherConfig:
    parser = argparse.ArgumentParser(description="5A Connect Log local HTTP launcher")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    app_root = Path(__file__).resolve().parent.parent
    return LauncherConfig(app_root=app_root, port=args.port, dry_run=args.dry_run)


def main() -> None:
    config = parse_args()
    with LauncherServer(config) as server:
        server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
