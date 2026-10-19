from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Final, Iterable, Literal, TypedDict
from zoneinfo import ZoneInfo


InstallPathSource = Literal["canonical", "legacy", "missing", "ambiguous"]
APP_RUNTIME_TOP_LEVEL_FILES: Final[tuple[str, ...]] = (
    "app.py",
    "APP_VERSION.txt",
    "requirements.txt",
)
APP_RUNTIME_SOURCE_GLOBS: Final[tuple[tuple[str, str], ...]] = (
    ("counsel_modules", "*.py"),
    ("prompts", "*.txt"),
)
APP_DISPLAY_TIMEZONE: Final[ZoneInfo] = ZoneInfo("Asia/Seoul")
RECORDING_AUTO_CLEANUP_SETTING_RELATIVE_PATH: Final[Path] = (
    Path("data") / "students" / "recording_auto_cleanup_enabled.txt"
)
RECORDING_AUTO_CLEANUP_FALSE_VALUES: Final[frozenset[str]] = frozenset(
    {"0", "false", "no", "off", "disabled"}
)


class BuildInfo(TypedDict):
    channel: str
    package_type: str
    version: str
    build_time: str
    last_updated_at: str


class RuntimeDiagnostics(TypedDict):
    current_runtime_path: str
    app_py_path: str
    expected_runtime_path: str
    is_expected_runtime_path: bool
    app_version: str
    build_info: BuildInfo


@dataclass(frozen=True, slots=True)
class InstallPathResolution:
    selected: Path | None
    candidates: tuple[Path, ...]
    source: InstallPathSource
    ambiguous: bool


def user_home_dir() -> Path:
    user_profile = os.environ.get("USERPROFILE", "").strip()
    return Path(user_profile) if user_profile else Path.home()


def canonical_app_dir(home_dir: Path | None = None) -> Path:
    if home_dir is None:
        override = os.environ.get("COUNSEL_NOTE_APP_DIR", "").strip()
        if override:
            return Path(override)
    return (home_dir or user_home_dir()) / "counsel-note-app"


def recording_auto_cleanup_enabled(base_dir: Path) -> bool:
    setting_path = base_dir / RECORDING_AUTO_CLEANUP_SETTING_RELATIVE_PATH
    try:
        configured_value = setting_path.read_text(encoding="utf-8-sig").strip().lower()
    except (OSError, UnicodeError):
        return True
    return configured_value not in RECORDING_AUTO_CLEANUP_FALSE_VALUES


def legacy_app_dirs(home_dir: Path | None = None) -> tuple[Path, ...]:
    home = home_dir or user_home_dir()
    return (
        home / "Desktop" / "counsel-note",
        home / "OneDrive" / "Desktop" / "counsel-note",
    )


def normalize_runtime_path(path: Path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _unique_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = normalize_runtime_path(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def resolve_install_target(
    existing_app_dirs: Iterable[Path],
    home_dir: Path | None = None,
) -> InstallPathResolution:
    existing = _unique_paths(existing_app_dirs)
    canonical = canonical_app_dir(home_dir)
    canonical_key = normalize_runtime_path(canonical)
    canonical_match = next(
        (path for path in existing if normalize_runtime_path(path) == canonical_key),
        None,
    )
    if canonical_match is not None:
        return InstallPathResolution(canonical_match, existing, "canonical", False)
    if len(existing) == 1:
        return InstallPathResolution(existing[0], existing, "legacy", False)
    if len(existing) > 1:
        return InstallPathResolution(None, existing, "ambiguous", True)
    return InstallPathResolution(None, (), "missing", False)


def is_expected_runtime_base_dir(
    current_path: Path,
    home_dir: Path | None = None,
) -> bool:
    return normalize_runtime_path(current_path) == normalize_runtime_path(canonical_app_dir(home_dir))


def read_app_version(path: Path) -> str:
    try:
        version = path.read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError):
        return "unknown"
    return version or "unknown"


def latest_app_runtime_modified_at(base_dir: Path) -> datetime | None:
    candidate_paths = tuple(base_dir / name for name in APP_RUNTIME_TOP_LEVEL_FILES)
    for relative_dir, pattern in APP_RUNTIME_SOURCE_GLOBS:
        candidate_paths += tuple((base_dir / relative_dir).glob(pattern))

    latest_mtime_ns: int | None = None
    for path in candidate_paths:
        try:
            mtime_ns = path.stat().st_mtime_ns
        except OSError:
            continue
        if latest_mtime_ns is None or mtime_ns > latest_mtime_ns:
            latest_mtime_ns = mtime_ns
    if latest_mtime_ns is None:
        return None
    return datetime.fromtimestamp(latest_mtime_ns / 1_000_000_000, APP_DISPLAY_TIMEZONE)


def format_app_last_modified_badge(base_dir: Path) -> str:
    modified_at = latest_app_runtime_modified_at(base_dir)
    if modified_at is None:
        return "마지막 업데이트: 알 수 없음"
    return f"마지막 업데이트: {modified_at:%Y-%m-%d %H:%M}"


def _empty_build_info() -> BuildInfo:
    return {
        "channel": "",
        "package_type": "",
        "version": "",
        "build_time": "",
        "last_updated_at": "",
    }


def read_build_info(path: Path) -> BuildInfo:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _empty_build_info()
    if not isinstance(payload, dict):
        return _empty_build_info()
    info = _empty_build_info()
    for key in info:
        info[key] = str(payload.get(key, "") or "")
    return info


def format_build_info_last_updated(build_info: BuildInfo) -> str:
    raw_value = build_info["last_updated_at"].strip()
    if not raw_value:
        return "알 수 없음"
    normalized = raw_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return raw_value[:16].replace("T", " ") or "알 수 없음"
    return parsed.strftime("%Y-%m-%d %H:%M")


def format_build_info_badge(build_info: BuildInfo) -> str:
    return f"마지막 업데이트: {format_build_info_last_updated(build_info)}"


def runtime_environment_diagnostics(
    *,
    base_dir: Path,
    app_py_path: Path,
    app_version_path: Path,
    build_info_path: Path,
    home_dir: Path | None = None,
) -> RuntimeDiagnostics:
    build_info = read_build_info(build_info_path)
    expected_path = canonical_app_dir(home_dir)
    return {
        "current_runtime_path": str(base_dir),
        "app_py_path": str(app_py_path),
        "expected_runtime_path": str(expected_path),
        "is_expected_runtime_path": is_expected_runtime_base_dir(base_dir, home_dir),
        "app_version": read_app_version(app_version_path),
        "build_info": build_info,
    }
