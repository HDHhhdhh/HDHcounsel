"""Run legacy regressions without importing the operational Streamlit app."""

from __future__ import annotations

import ast
import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from counsel_modules.local_consumed_admin_notes import _save_status_is_consumable

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def load_nodes(nodes, namespace):
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        *nodes,
    ], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, str(APP_PATH), "exec"), namespace)


class LegacyReviewRegressions(unittest.TestCase):
    def test_c1_first_row_consumption_and_retry_statuses(self):
        tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
        functions = {
            node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        guard = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.BoolOp)
            and isinstance(node.test.values[0], ast.Name)
            and node.test.values[0].id == "consumed_filter_enabled"
        )
        marked = []

        def mark_notes(name, sid, notes, status, **kwargs):
            if _save_status_is_consumable(status):
                marked.append(name)
                return {"marked_count": 1}
            return {"marked_count": 0}

        namespace = {
            "mark_admin_notes_consumed": mark_notes,
            "extract_consumable_admin_section_notes_from_docs_text": lambda text: [],
            "build_log_csv_duplicate_summary_fingerprint": lambda text: "",
        }
        load_nodes([
            functions["is_truthy_result_value"],
            functions["mark_consumed_admin_notes_for_saved_row"],
            functions["build_log_csv_to_docs_result_entry"],
        ], namespace)
        for index in (0, 1):
            for status in ("success", "saved_confirmed_after_timeout", "failed", "needs_review"):
                with self.subTest(index=index, status=status):
                    row = {"name": f"TEST-{index}", "notes": "synthetic note"}
                    result = namespace["build_log_csv_to_docs_result_entry"](
                        row, status, "", source_index=index,
                        retry_attempt=1 if status == "saved_confirmed_after_timeout" else "",
                    )
                    namespace.update(
                        consumed_filter_enabled=True, results=[result],
                        selected_index=index, row=row, final_docs_summary="synthetic note",
                    )
                    marked.clear()
                    load_nodes([guard], namespace)
                    self.assertEqual(
                        marked,
                        [row["name"]] if _save_status_is_consumable(status) else [],
                    )
                    self.assertNotIn("admin_consumed_mark_error", result)
        namespace["results"] = [{"source_index": None}]
        namespace["selected_index"] = 0
        marked.clear()
        load_nodes([guard], namespace)
        self.assertEqual(marked, [])

    def test_c2_same_name_and_size_use_new_recording_bytes(self):
        tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
        names = {
            "handle_audio_upload_change", "validate_uploaded_extension",
            "safe_upload_path", "save_uploaded_file_copy",
        }
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
        with tempfile.TemporaryDirectory() as directory:
            state = {}
            namespace = {
                "Path": Path, "hashlib": hashlib,
                "st": SimpleNamespace(session_state=state),
                "UPLOAD_DIR": Path(directory), "ALLOWED_EXTENSIONS": {"wav"},
                "sanitize_filename_part": lambda value: value,
                "queue_student_name_from_audio_filename": lambda name: None,
            }
            load_nodes(nodes, namespace)

            def upload(data):
                file = SimpleNamespace(name="same.wav", size=len(data), getbuffer=lambda: data)
                state["audio_upload"] = [file]
                namespace["handle_audio_upload_change"]()
                return namespace["save_uploaded_file_copy"](file)

            first = upload(b"AAAA")
            self.assertEqual(first.read_bytes(), b"AAAA")
            second = upload(b"BBBB")
            self.assertNotEqual(first, second)
            self.assertEqual(first.read_bytes(), b"AAAA")
            self.assertEqual(second.read_bytes(), b"BBBB")
            self.assertEqual(upload(b"BBBB"), second)
            self.assertEqual(len(list(Path(directory).iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
