from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Literal


CodexExecutableKind = Literal["codex_cmd", "codex"]
CodexLoginState = Literal["authenticated", "not_authenticated", "unknown"]


@dataclass(frozen=True, slots=True)
class CodexExecutable:
    kind: CodexExecutableKind
    path: Path
    fixed_path: Path | None
    ignored_windowsapps: str


@dataclass(frozen=True, slots=True)
class CodexLoginStatus:
    state: CodexLoginState
    detail: str
    returncode: int | None


def fixed_windows_codex_path(home_dir: Path | None = None) -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata and home_dir is None:
        return Path(appdata) / "npm" / "codex.cmd"
    home = home_dir or Path.home()
    return home / "AppData" / "Roaming" / "npm" / "codex.cmd"


def bundled_windows_codex_path(command_path: Path | None = None) -> Path | None:
    npm_root = (command_path or fixed_windows_codex_path()).parent
    package_root = npm_root / "node_modules" / "@openai" / "codex" / "node_modules" / "@openai"
    machine = platform.machine().casefold()
    architecture = "arm64" if "arm" in machine else "x64"
    preferred = package_root.glob(f"codex-win32-{architecture}/vendor/*/bin/codex.exe")
    candidates = [*preferred, *package_root.glob("codex-win32-*/vendor/*/bin/codex.exe")]
    return next((path for path in candidates if path.is_file()), None)


def is_windowsapps_path(path: str | None) -> bool:
    return bool(path and "windowsapps" in path.casefold())


def codex_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(base_env or os.environ)
    if sys.platform.startswith("win"):
        roaming_npm = str(fixed_windows_codex_path().parent)
        current_path = env.get("PATH", "")
        env["PATH"] = os.pathsep.join([roaming_npm, r"C:\Program Files\nodejs", current_path])
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["NO_COLOR"] = "1"
    return env


def find_codex_executable() -> CodexExecutable | None:
    if sys.platform.startswith("win"):
        fixed_path = fixed_windows_codex_path()
        discovered_path = shutil.which("codex") or ""
        bundled_path = bundled_windows_codex_path(fixed_path)
        if bundled_path is not None:
            return CodexExecutable(
                kind="codex",
                path=bundled_path,
                fixed_path=fixed_path if fixed_path.exists() else None,
                ignored_windowsapps=discovered_path if is_windowsapps_path(discovered_path) else "",
            )
        if (
            discovered_path
            and not is_windowsapps_path(discovered_path)
            and Path(discovered_path).suffix.casefold() == ".exe"
        ):
            return CodexExecutable(
                kind="codex",
                path=Path(discovered_path),
                fixed_path=fixed_path if fixed_path.exists() else None,
                ignored_windowsapps="",
            )
        if not fixed_path.exists():
            return None
        return CodexExecutable(
            kind="codex_cmd",
            path=fixed_path,
            fixed_path=fixed_path,
            ignored_windowsapps=discovered_path,
        )
    codex_path = shutil.which("codex")
    if not codex_path:
        return None
    return CodexExecutable(
        kind="codex",
        path=Path(codex_path),
        fixed_path=None,
        ignored_windowsapps="",
    )


def codex_command(
    executable: CodexExecutable,
    *arguments: str,
    comspec: str | None = None,
) -> tuple[str, ...]:
    direct = (str(executable.path), *arguments)
    if executable.kind == "codex":
        return direct
    command_shell = comspec or os.environ.get("COMSPEC", "cmd.exe")
    return (command_shell, "/d", "/s", "/c", f"call {subprocess.list2cmdline(direct)}")


def check_codex_login_status(
    executable: CodexExecutable,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int = 10,
) -> CodexLoginStatus:
    command = codex_command(executable, "login", "status")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(cwd),
            env=env,
            shell=False,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return CodexLoginStatus("unknown", "Codex login status timed out.", None)
    except OSError as exc:
        return CodexLoginStatus("unknown", str(exc), None)

    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    if "not logged in" in output.casefold():
        return CodexLoginStatus("not_authenticated", output, completed.returncode)
    if completed.returncode == 0:
        return CodexLoginStatus("authenticated", output or "Logged in", completed.returncode)
    return CodexLoginStatus("unknown", output or "Codex login status was unavailable.", completed.returncode)


def launch_codex_login_window(
    executable: CodexExecutable,
    *,
    cwd: Path,
    env: dict[str, str],
) -> None:
    command = codex_command(executable, "login")
    creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0) if sys.platform.startswith("win") else 0
    subprocess.Popen(
        command,
        cwd=str(cwd),
        env=env,
        shell=False,
        creationflags=creationflags,
    )
