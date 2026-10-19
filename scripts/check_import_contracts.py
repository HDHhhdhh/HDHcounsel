from __future__ import annotations

import ast
import importlib
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


DIRECT_IMPORT_CHECKS = (
    ("counsel_modules.google_docs_utils", "classify_google_docs_timeout_verification"),
    ("counsel_modules.log_csv_utils", "classify_google_docs_save_result"),
)


def iter_counsel_module_imports(source_path: Path) -> list[tuple[int, str, str]]:
    tree = ast.parse(source_path.read_text(encoding="utf-8-sig"), filename=str(source_path))
    imports: list[tuple[int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module_name = node.module or ""
        if not module_name.startswith("counsel_modules."):
            continue
        for alias in node.names:
            if alias.name == "*":
                continue
            imports.append((node.lineno, module_name, alias.name))
    return imports


def check_module_has_name(module_name: str, import_name: str) -> str:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - surfaced by CLI output
        return f"{module_name}: module import failed: {exc}"
    if not hasattr(module, import_name):
        return f"{module_name}: missing {import_name}"
    return ""


def main() -> int:
    app_path = ROOT_DIR / "app.py"
    failures: list[str] = []

    for lineno, module_name, import_name in iter_counsel_module_imports(app_path):
        error = check_module_has_name(module_name, import_name)
        if error:
            failures.append(f"{app_path.name}:{lineno}: {error}")

    for module_name, import_name in DIRECT_IMPORT_CHECKS:
        error = check_module_has_name(module_name, import_name)
        if error:
            failures.append(f"direct smoke: {error}")

    if failures:
        print("import contract check failed")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("import contracts ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
