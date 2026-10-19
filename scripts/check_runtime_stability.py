from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from unittest.mock import patch
from zoneinfo import ZoneInfo


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def check_canonical_install_path_uses_user_profile_root() -> None:
    from counsel_modules.runtime_utils import canonical_app_dir

    home = Path("C:/Users/example")

    assert canonical_app_dir(home) == home / "counsel-note-app"


def check_install_path_resolution_prefers_canonical_path() -> None:
    from counsel_modules.runtime_utils import canonical_app_dir, resolve_install_target

    home = Path("C:/Users/example")
    canonical = canonical_app_dir(home)
    legacy = home / "Desktop" / "counsel-note"

    resolution = resolve_install_target([legacy, canonical], home)

    assert resolution.selected == canonical
    assert resolution.source == "canonical"
    assert resolution.ambiguous is False


def check_install_path_resolution_refuses_multiple_legacy_paths() -> None:
    from counsel_modules.runtime_utils import resolve_install_target

    home = Path("C:/Users/example")
    desktop = home / "Desktop" / "counsel-note"
    onedrive = home / "OneDrive" / "Desktop" / "counsel-note"

    resolution = resolve_install_target([desktop, onedrive], home)

    assert resolution.selected is None
    assert resolution.source == "ambiguous"
    assert resolution.ambiguous is True


def check_app_last_modified_uses_latest_runtime_source_only() -> None:
    from counsel_modules.runtime_utils import (
        format_app_last_modified_badge,
        latest_app_runtime_modified_at,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        runtime_files = {
            root / "app.py": 1_700_000_000,
            root / "APP_VERSION.txt": 1_700_000_030,
            root / "requirements.txt": 1_700_000_090,
            root / "counsel_modules" / "worker.py": 1_700_000_060,
            root / "prompts" / "summary_ko.txt": 1_700_000_120,
        }
        ignored_files = {
            root / "BUILD_INFO.json": 1_700_000_180,
            root / "data" / "drafts" / "current.json": 1_700_000_240,
        }
        for path, modified_at in (runtime_files | ignored_files).items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("sample", encoding="utf-8")
            os.utime(path, (modified_at, modified_at))

        latest = latest_app_runtime_modified_at(root)

        assert latest is not None
        assert int(latest.timestamp()) == 1_700_000_120
        expected = datetime.fromtimestamp(1_700_000_120, ZoneInfo("Asia/Seoul"))
        assert format_app_last_modified_badge(root) == (
            f"마지막 업데이트: {expected:%Y-%m-%d %H:%M}"
        )
        assert format_app_last_modified_badge(root / "missing") == "마지막 업데이트: 알 수 없음"


def check_recording_auto_cleanup_can_be_disabled_per_install() -> None:
    from counsel_modules.runtime_utils import (
        RECORDING_AUTO_CLEANUP_SETTING_RELATIVE_PATH,
        recording_auto_cleanup_enabled,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        setting_path = root / RECORDING_AUTO_CLEANUP_SETTING_RELATIVE_PATH

        assert recording_auto_cleanup_enabled(root) is True

        setting_path.parent.mkdir(parents=True, exist_ok=True)
        setting_path.write_text("false\n", encoding="utf-8")
        assert recording_auto_cleanup_enabled(root) is False

        setting_path.write_text("true\n", encoding="utf-8")
        assert recording_auto_cleanup_enabled(root) is True

    app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    assert "if not _recording_auto_cleanup_enabled(BASE_DIR):" in app_source

    builder_source = (
        ROOT_DIR / "scripts" / "make_new_pc_bootstrap_zip.ps1"
    ).read_text(encoding="utf-8")
    assert "[switch]$DisableRecordingAutoCleanup" in builder_source
    assert "recording_auto_cleanup_enabled.txt" in builder_source


def check_codex_invocations_use_direct_cmd_before_powershell_fallback() -> None:
    from counsel_modules.codex_runner import CodexExecutable, build_codex_invocations

    executable = CodexExecutable(
        kind="codex_cmd",
        path=Path("C:/Users/example/AppData/Roaming/npm/codex.cmd"),
        fixed_path=Path("C:/Users/example/AppData/Roaming/npm/codex.cmd"),
        ignored_windowsapps="",
    )

    invocations = build_codex_invocations(
        executable=executable,
        model="gpt-test",
        instruction="instruction",
        prompt="prompt body",
        input_path=Path("C:/tmp/input.txt"),
        platform="win32",
        comspec="C:/Windows/System32/cmd.exe",
    )

    assert [invocation.kind for invocation in invocations] == ["cmd_stdin", "powershell_file"]
    assert invocations[0].stdin_text == "prompt body"
    assert invocations[1].stdin_text is None
    assert invocations[0].command[-1].startswith("call ")
    assert not invocations[0].command[-1].startswith('"')


def check_windows_codex_discovery_falls_back_to_path_native_executable() -> None:
    from counsel_modules.codex_runner import find_codex_executable

    with tempfile.TemporaryDirectory() as temp_dir:
        native_path = "C:/Users/example/.codex/bin/codex.EXE"
        with (
            patch.dict(os.environ, {"APPDATA": temp_dir}),
            patch("counsel_modules.codex_runtime.sys.platform", "win32"),
            patch("counsel_modules.codex_runtime.shutil.which", return_value=native_path),
        ):
            executable = find_codex_executable()

    assert executable is not None
    assert executable.kind == "codex"
    assert executable.path == Path(native_path)


def check_windows_codex_discovery_prefers_bundled_install_over_path_executable() -> None:
    from counsel_modules.codex_runner import find_codex_executable

    with tempfile.TemporaryDirectory() as temp_dir:
        appdata = Path(temp_dir)
        command_path = appdata / "npm" / "codex.cmd"
        bundled_path = (
            appdata
            / "npm"
            / "node_modules"
            / "@openai"
            / "codex"
            / "node_modules"
            / "@openai"
            / "codex-win32-x64"
            / "vendor"
            / "x86_64-pc-windows-msvc"
            / "bin"
            / "codex.exe"
        )
        command_path.parent.mkdir(parents=True, exist_ok=True)
        bundled_path.parent.mkdir(parents=True, exist_ok=True)
        command_path.write_text("@echo off", encoding="utf-8")
        bundled_path.write_bytes(b"")

        with (
            patch.dict(os.environ, {"APPDATA": str(appdata)}),
            patch("counsel_modules.codex_runtime.sys.platform", "win32"),
            patch(
                "counsel_modules.codex_runtime.shutil.which",
                return_value="C:/Users/example/.codex/bin/codex.EXE",
            ),
        ):
            executable = find_codex_executable()

    assert executable is not None
    assert executable.kind == "codex"
    assert executable.path == bundled_path


def check_windows_codex_discovery_finds_bundled_native_executable() -> None:
    from counsel_modules.codex_runner import find_codex_executable

    with tempfile.TemporaryDirectory() as temp_dir:
        appdata = Path(temp_dir)
        command_path = appdata / "npm" / "codex.cmd"
        native_path = (
            appdata
            / "npm"
            / "node_modules"
            / "@openai"
            / "codex"
            / "node_modules"
            / "@openai"
            / "codex-win32-x64"
            / "vendor"
            / "x86_64-pc-windows-msvc"
            / "bin"
            / "codex.exe"
        )
        command_path.parent.mkdir(parents=True, exist_ok=True)
        native_path.parent.mkdir(parents=True, exist_ok=True)
        command_path.write_text("@echo off", encoding="utf-8")
        native_path.write_bytes(b"")

        with (
            patch.dict(os.environ, {"APPDATA": str(appdata)}),
            patch("counsel_modules.codex_runtime.sys.platform", "win32"),
            patch("counsel_modules.codex_runtime.shutil.which", return_value=str(command_path)),
        ):
            executable = find_codex_executable()

    assert executable is not None
    assert executable.kind == "codex"
    assert executable.path == native_path


def check_codex_login_status_reports_signed_out() -> None:
    from counsel_modules.codex_runner import CodexExecutable, check_codex_login_status

    executable = CodexExecutable(
        kind="codex",
        path=Path("C:/tools/codex.exe"),
        fixed_path=None,
        ignored_windowsapps="",
    )
    completed = subprocess.CompletedProcess(
        (str(executable.path), "login", "status"),
        1,
        "",
        "Not logged in",
    )

    with patch("counsel_modules.codex_runtime.subprocess.run", return_value=completed):
        status = check_codex_login_status(
            executable,
            cwd=Path("C:/app"),
            env={"PATH": "C:/tools"},
        )

    assert status.state == "not_authenticated"
    assert status.returncode == 1


def check_codex_login_window_uses_native_executable() -> None:
    from counsel_modules.codex_runner import CodexExecutable, launch_codex_login_window

    executable = CodexExecutable(
        kind="codex",
        path=Path("C:/tools/codex.exe"),
        fixed_path=None,
        ignored_windowsapps="",
    )

    with (
        patch("counsel_modules.codex_runtime.sys.platform", "win32"),
        patch("counsel_modules.codex_runtime.subprocess.Popen") as popen,
    ):
        launch_codex_login_window(
            executable,
            cwd=Path("C:/app"),
            env={"PATH": "C:/tools"},
        )

    command = popen.call_args.args[0]
    assert Path(command[0]) == Path("C:/tools/codex.exe")
    assert command[1:] == ("login",)
    assert popen.call_args.kwargs["shell"] is False


def check_codex_invocations_pin_model_and_reasoning_effort() -> None:
    from counsel_modules.codex_runner import CodexExecutable, build_codex_invocations

    executable = CodexExecutable(
        kind="codex",
        path=Path("C:/tools/codex.exe"),
        fixed_path=None,
        ignored_windowsapps="",
    )

    invocation = build_codex_invocations(
        executable=executable,
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        instruction="instruction",
        prompt="prompt body",
        input_path=Path("C:/tmp/input.txt"),
        platform="win32",
    )[0]

    assert "--model" in invocation.command
    assert "gpt-5.6-sol" in invocation.command
    assert "-c" in invocation.command
    assert 'model_reasoning_effort="medium"' in invocation.command


def check_native_windows_codex_runs_without_cmd_wrapper() -> None:
    from counsel_modules.codex_runner import CodexExecutable, build_codex_invocations

    executable = CodexExecutable(
        kind="codex",
        path=Path("C:/Users/example/.codex/bin/codex.exe"),
        fixed_path=None,
        ignored_windowsapps="",
    )

    invocations = build_codex_invocations(
        executable=executable,
        model="gpt-test",
        instruction="instruction",
        prompt="prompt body",
        input_path=Path("C:/tmp/input.txt"),
        platform="win32",
    )

    assert invocations[0].kind == "direct_stdin"
    assert invocations[0].command[0] == str(executable.path)


def check_codex_fallback_runs_only_for_invocation_failures() -> None:
    from counsel_modules.codex_runner import should_try_alternate_invocation

    assert should_try_alternate_invocation("invocation") is True
    assert should_try_alternate_invocation("empty_output") is True
    assert should_try_alternate_invocation("usage_limit") is False
    assert should_try_alternate_invocation("authentication") is False
    assert should_try_alternate_invocation("permission") is False


def check_codex_authentication_failure_recognizes_logged_out_cli() -> None:
    from counsel_modules.codex_runner import classify_codex_failure_category

    assert classify_codex_failure_category("", "Not logged in") == "authentication"


def check_codex_network_failure_recognizes_blocked_socket() -> None:
    from counsel_modules.codex_runner import classify_codex_failure_category

    stderr = "stream disconnected before completion: hidden socket access was denied (os error 10013)"

    assert classify_codex_failure_category("", stderr) == "network"


def check_codex_bad_cmd_syntax_uses_alternate_invocation() -> None:
    from counsel_modules.codex_runner import classify_codex_failure_category

    stderr = "The filename, directory name, or volume label syntax is incorrect."

    assert classify_codex_failure_category("", stderr) == "invocation"


def check_codex_unexpected_prompt_argument_uses_alternate_invocation() -> None:
    from counsel_modules.codex_runner import classify_codex_failure_category

    stderr = "error: unexpected argument '표준입력의' found\n\nUsage: codex exec [OPTIONS] [PROMPT]"

    assert classify_codex_failure_category("", stderr) == "invocation"


def check_codex_execution_retries_with_alternate_invocation() -> None:
    from counsel_modules.codex_runner import CodexInvocation, run_codex_invocations

    invocations = (
        CodexInvocation(kind="cmd_stdin", command=("cmd.exe",), stdin_text="prompt"),
        CodexInvocation(kind="powershell_file", command=("powershell.exe",), stdin_text=None),
    )
    completed = [
        subprocess.CompletedProcess(invocations[0].command, 1, "", "is not recognized"),
        subprocess.CompletedProcess(invocations[1].command, 0, "valid summary output", ""),
    ]

    with patch("counsel_modules.codex_runner.subprocess.run", side_effect=completed) as run:
        result = run_codex_invocations(
            invocations,
            cwd=Path("C:/app"),
            env={"PATH": "C:/bin"},
            timeout_seconds=10,
        )

    assert result.invocation_kind == "powershell_file"
    assert result.stdout == "valid summary output"
    assert result.attempt_count == 2
    assert run.call_count == 2


def check_codex_execution_does_not_retry_usage_limit() -> None:
    from counsel_modules.codex_runner import CodexExecutionError, CodexInvocation, run_codex_invocations

    invocations = (
        CodexInvocation(kind="cmd_stdin", command=("cmd.exe",), stdin_text="prompt"),
        CodexInvocation(kind="powershell_file", command=("powershell.exe",), stdin_text=None),
    )
    completed = subprocess.CompletedProcess(
        invocations[0].command,
        1,
        "",
        "You've hit your usage limit. Try again at 10:00.",
    )

    with patch("counsel_modules.codex_runner.subprocess.run", return_value=completed) as run:
        try:
            run_codex_invocations(
                invocations,
                cwd=Path("C:/app"),
                env={"PATH": "C:/bin"},
                timeout_seconds=10,
            )
        except CodexExecutionError as exc:
            assert exc.category == "usage_limit"
            assert exc.attempt_count == 1
        else:
            raise AssertionError("usage-limit failure must stop without a second Codex call")

    assert run.call_count == 1


def check_codex_execution_preserves_useful_fallback_error() -> None:
    from counsel_modules.codex_runner import CodexExecutionError, CodexInvocation, run_codex_invocations

    invocations = (
        CodexInvocation(kind="cmd_stdin", command=("cmd.exe",), stdin_text="prompt"),
        CodexInvocation(kind="powershell_file", command=("powershell.exe",), stdin_text=None),
    )
    completed = [
        subprocess.CompletedProcess(invocations[0].command, 1, "", "broken pipe while starting"),
        subprocess.CompletedProcess(invocations[1].command, 1, "", ""),
    ]

    with patch("counsel_modules.codex_runner.subprocess.run", side_effect=completed):
        try:
            run_codex_invocations(
                invocations,
                cwd=Path("C:/app"),
                env={"PATH": "C:/bin"},
                timeout_seconds=10,
            )
        except CodexExecutionError as exc:
            assert exc.stderr == "broken pipe while starting"
            assert exc.attempt_count == 2
        else:
            raise AssertionError("failed fallback must preserve the useful first error")


def check_summary_actions_preflight_codex_login() -> None:
    source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    callback_start = source.index("def start_single_consultation_job() -> None:")
    callback_end = source.index("if upload_mode in", callback_start)
    callback = source[callback_start:callback_end]

    assert callback.index("prepare_codex_summary_processing()") < callback.index(
        'st.session_state["is_processing"] = True'
    )
    assert 'st.button("Codex 로그인 열기"' in source
    assert "render_codex_login_recovery(ui_locked)" in source


def check_packaging_scripts_use_canonical_install_path() -> None:
    update_builder = (ROOT_DIR / "scripts" / "make_sebin_update_zip.ps1").read_text(
        encoding="utf-8"
    )
    new_pc_builder = (ROOT_DIR / "scripts" / "make_new_pc_bootstrap_zip.ps1").read_text(
        encoding="utf-8"
    )
    auto_updater = (ROOT_DIR / "scripts" / "sebin_check_and_apply_update.ps1").read_text(
        encoding="utf-8"
    )
    emergency_installer = (
        ROOT_DIR / "scripts" / "sebin_emergency_oneclick_install.ps1"
    ).read_text(encoding="utf-8")

    canonical_batch_target = 'set "TARGET=%USERPROFILE%\\counsel-note-app"'
    canonical_powershell_target = '$target = Join-Path $env:USERPROFILE "counsel-note-app"'
    assert update_builder.count(canonical_batch_target) >= 2
    assert canonical_powershell_target in new_pc_builder
    assert '$DefaultInstallRoot = Join-Path $env:USERPROFILE "counsel-note-app"' in auto_updater
    assert '$targetRoot = Join-Path $env:USERPROFILE "counsel-note-app"' in emergency_installer
    assert 'set "TARGET=%USERPROFILE%\\Desktop\\counsel-note"' not in new_pc_builder
    assert 'set "TARGET=%USERPROFILE%\\OneDrive\\Desktop\\counsel-note"' not in update_builder


def check_new_pc_builder_includes_quick_check_dependencies() -> None:
    quick_check = (ROOT_DIR / "scripts" / "check_quick.ps1").read_text(encoding="utf-8")
    builder = (ROOT_DIR / "scripts" / "make_new_pc_bootstrap_zip.ps1").read_text(
        encoding="utf-8"
    )
    referenced_scripts = set(re.findall(r'@\("scripts\\([^"\\]+\.py)"\)', quick_check))
    referenced_scripts.add("ui_contract_fixture.py")

    assert referenced_scripts
    for script_name in referenced_scripts:
        assert builder.count(script_name) >= 2, script_name


def check_consumed_registry_save_retries_transient_permission_error() -> None:
    from counsel_modules.local_consumed_admin_notes import save_consumed_admin_notes

    original_replace = Path.replace
    attempts = 0

    def transiently_locked_replace(source: Path, target: Path) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError(13, "transient Windows file lock", str(target))
        return original_replace(source, target)

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        with patch("pathlib.Path.replace", new=transiently_locked_replace):
            result = save_consumed_admin_notes(
                {"version": 2, "items": []},
                registry_path,
            )

        assert result["ok"] is True
        assert registry_path.exists()
        assert attempts == 2


def main() -> None:
    check_canonical_install_path_uses_user_profile_root()
    check_install_path_resolution_prefers_canonical_path()
    check_install_path_resolution_refuses_multiple_legacy_paths()
    check_app_last_modified_uses_latest_runtime_source_only()
    check_recording_auto_cleanup_can_be_disabled_per_install()
    check_codex_invocations_use_direct_cmd_before_powershell_fallback()
    check_windows_codex_discovery_falls_back_to_path_native_executable()
    check_windows_codex_discovery_prefers_bundled_install_over_path_executable()
    check_windows_codex_discovery_finds_bundled_native_executable()
    check_codex_login_status_reports_signed_out()
    check_codex_login_window_uses_native_executable()
    check_codex_invocations_pin_model_and_reasoning_effort()
    check_native_windows_codex_runs_without_cmd_wrapper()
    check_codex_fallback_runs_only_for_invocation_failures()
    check_codex_authentication_failure_recognizes_logged_out_cli()
    check_codex_network_failure_recognizes_blocked_socket()
    check_codex_bad_cmd_syntax_uses_alternate_invocation()
    check_codex_unexpected_prompt_argument_uses_alternate_invocation()
    check_codex_execution_retries_with_alternate_invocation()
    check_codex_execution_does_not_retry_usage_limit()
    check_codex_execution_preserves_useful_fallback_error()
    check_summary_actions_preflight_codex_login()
    check_packaging_scripts_use_canonical_install_path()
    check_new_pc_builder_includes_quick_check_dependencies()
    check_consumed_registry_save_retries_transient_permission_error()
    print("runtime stability checks passed")


if __name__ == "__main__":
    main()
