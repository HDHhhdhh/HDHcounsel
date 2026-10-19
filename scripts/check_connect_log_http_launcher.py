# /// script
# requires-python = ">=3.11"
# ///
# How to run: python check_connect_log_http_launcher.py

from __future__ import annotations

import http.client
import socket
import subprocess
import sys
import time
from pathlib import Path


def reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.bind(("127.0.0.1", 0))
        return int(server_socket.getsockname()[1])


def request(port: int, path: str) -> tuple[int, str, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, response.getheader("Location", ""), response.read().decode("utf-8")
    finally:
        connection.close()


def wait_until_ready(port: int) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            status, _, body = request(port, "/health")
        except (ConnectionError, OSError):
            time.sleep(0.05)
            continue
        if status == 200 and body == "ok":
            return
    raise AssertionError("launcher did not become ready")


def main() -> None:
    launcher_path = Path(__file__).with_name("connect_log_http_launcher.py")
    port = reserve_port()
    process = subprocess.Popen(
        [sys.executable, str(launcher_path), "--port", str(port), "--dry-run"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_until_ready(port)

        status, location, _ = request(port, "/open")
        assert status == 302
        assert location == "http://localhost:8501"

        status, _, _ = request(port, "/missing")
        assert status == 404
    finally:
        process.terminate()
        try:
            _, stderr = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate(timeout=3)

    if process.returncode not in (0, -15, 1):
        raise AssertionError(stderr)
    print("connect_log_http_launcher checks passed")


if __name__ == "__main__":
    main()
