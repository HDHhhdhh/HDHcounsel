from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import subprocess
import sys
from typing import Literal

from counsel_modules.codex_runtime import (
    CodexExecutable,
    CodexLoginStatus,
    check_codex_login_status,
    codex_env,
    find_codex_executable,
    fixed_windows_codex_path,
    is_windowsapps_path,
    launch_codex_login_window,
)


CodexInvocationKind = Literal["cmd_stdin", "powershell_file", "direct_stdin"]
CodexFailureCategory = Literal[
    "usage_limit",
    "authentication",
    "network",
    "permission",
    "invocation",
    "empty_output",
    "unknown",
]


@dataclass(frozen=True, slots=True)
class CodexInvocation:
    kind: CodexInvocationKind
    command: tuple[str, ...]
    stdin_text: str | None


@dataclass(frozen=True, slots=True)
class CodexExecutionResult:
    stdout: str
    stderr: str
    returncode: int
    invocation_kind: CodexInvocationKind
    command: tuple[str, ...]
    attempt_count: int


@dataclass(frozen=True, slots=True)
class CodexExecutionError(RuntimeError):
    category: CodexFailureCategory
    stdout: str
    stderr: str
    returncode: int | None
    invocation_kind: CodexInvocationKind | None
    command: tuple[str, ...]
    attempt_count: int
    detail: str

    def __str__(self) -> str:
        return self.detail


def _powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_codex_invocations(
    *,
    executable: CodexExecutable,
    model: str | None,
    instruction: str,
    prompt: str,
    input_path: Path,
    reasoning_effort: str | None = None,
    platform: str | None = None,
    comspec: str | None = None,
) -> tuple[CodexInvocation, ...]:
    selected_platform = platform or sys.platform
    codex_args_list = [
        str(executable.path),
        "exec",
        "--ephemeral",
        "--skip-git-repo-check",
    ]
    selected_model = str(model or "").strip()
    if selected_model:
        codex_args_list.extend(["--model", selected_model])
    selected_reasoning_effort = str(reasoning_effort or "").strip()
    reasoning_config = (
        f'model_reasoning_effort="{selected_reasoning_effort}"'
        if selected_reasoning_effort
        else ""
    )
    if selected_reasoning_effort:
        codex_args_list.extend(["-c", reasoning_config])
    codex_args_list.append(instruction)
    codex_args = tuple(codex_args_list)
    if not selected_platform.startswith("win"):
        return (CodexInvocation("direct_stdin", codex_args, prompt),)

    powershell_command_text = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [System.Text.Encoding]::UTF8; "
        f"Get-Content -Raw -Encoding UTF8 {_powershell_quote(str(input_path))} | "
        f"& {_powershell_quote(str(executable.path))} exec --ephemeral --skip-git-repo-check"
        f"{f' --model {_powershell_quote(selected_model)}' if selected_model else ''} "
        f"{f' -c {_powershell_quote(reasoning_config)}' if reasoning_config else ''} "
        f"{_powershell_quote(instruction)}"
    )
    powershell_command = (
        "powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        powershell_command_text,
    )
    if executable.kind == "codex":
        return (
            CodexInvocation("direct_stdin", codex_args, prompt),
            CodexInvocation("powershell_file", powershell_command, None),
        )

    command_shell = comspec or os.environ.get("COMSPEC", "cmd.exe")
    command_text = subprocess.list2cmdline(codex_args)
    direct_command = (command_shell, "/d", "/s", "/c", f"call {command_text}")
    return (
        CodexInvocation("cmd_stdin", direct_command, prompt),
        CodexInvocation("powershell_file", powershell_command, None),
    )


def classify_codex_failure_category(stdout: str, stderr: str) -> CodexFailureCategory:
    combined = f"{stdout}\n{stderr}".casefold()
    if any(phrase in combined for phrase in ("usage limit", "try again at", "upgrade to plus")):
        return "usage_limit"
    if any(
        phrase in combined
        for phrase in ("not authenticated", "not logged in", "authentication", "login required")
    ):
        return "authentication"
    if any(
        phrase in combined
        for phrase in (
            "os error 10013",
            "stream disconnected before completion",
            "error sending request",
            "failed to connect",
        )
    ):
        return "network"
    if any(phrase in combined for phrase in ("access is denied", "permission denied")):
        return "permission"
    if any(
        phrase in combined
        for phrase in (
            "is not recognized",
            "내부 또는 외부 명령",
            "volume label syntax is incorrect",
            "볼륨 레이블 구문이 잘못",
            "unexpected argument",
            "winerror",
            "broken pipe",
        )
    ):
        return "invocation"
    return "unknown"


def should_try_alternate_invocation(category: CodexFailureCategory) -> bool:
    return category in {"invocation", "empty_output"}


def run_codex_invocations(
    invocations: tuple[CodexInvocation, ...],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: int,
) -> CodexExecutionResult:
    last_error: CodexExecutionError | None = None
    best_error: CodexExecutionError | None = None
    for attempt_count, invocation in enumerate(invocations, start=1):
        try:
            completed = subprocess.run(
                invocation.command,
                input=invocation.stdin_text,
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
        except PermissionError as exc:
            raise CodexExecutionError(
                "permission",
                "",
                str(exc),
                None,
                invocation.kind,
                invocation.command,
                attempt_count,
                "Codex CLI execution permission was denied.",
            ) from exc
        except OSError as exc:
            category: CodexFailureCategory = "invocation"
            last_error = CodexExecutionError(
                category,
                "",
                str(exc),
                None,
                invocation.kind,
                invocation.command,
                attempt_count,
                "Codex CLI process could not be started.",
            )
        else:
            if completed.returncode == 0 and completed.stdout.strip():
                return CodexExecutionResult(
                    completed.stdout,
                    completed.stderr,
                    completed.returncode,
                    invocation.kind,
                    invocation.command,
                    attempt_count,
                )
            category = (
                "empty_output"
                if completed.returncode == 0
                else classify_codex_failure_category(completed.stdout, completed.stderr)
            )
            last_error = CodexExecutionError(
                category,
                completed.stdout,
                completed.stderr,
                completed.returncode,
                invocation.kind,
                invocation.command,
                attempt_count,
                "Codex CLI did not return a usable result.",
            )
        if last_error is not None:
            current_detail_length = len(last_error.stdout.strip()) + len(last_error.stderr.strip())
            best_detail_length = (
                len(best_error.stdout.strip()) + len(best_error.stderr.strip()) if best_error else -1
            )
            if best_error is None or current_detail_length > best_detail_length:
                best_error = last_error
            if not should_try_alternate_invocation(last_error.category):
                raise replace(best_error or last_error, attempt_count=attempt_count)
    if last_error is None:
        raise CodexExecutionError(
            "invocation",
            "",
            "",
            None,
            None,
            (),
            0,
            "No Codex CLI invocation was available.",
        )
    selected_error = best_error or last_error
    raise replace(selected_error, attempt_count=len(invocations))
