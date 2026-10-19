from __future__ import annotations

import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, get_ident
from unittest.mock import patch

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from counsel_modules.log_csv_batch_state import create_log_csv_batch_state, load_log_csv_batch_state, save_log_csv_batch_state
from counsel_modules.log_csv_processing_history import empty_log_csv_processing_history, load_log_csv_processing_history, save_log_csv_processing_history


def main() -> None:
    import os

    state = create_log_csv_batch_state(
        upload_signature="test", source_csv_name="test.csv", source_csv_size=1,
        source_csv_path="", source_mtime_ns=0, selected_indices=[0, 1],
        started_at="2026-09-06T12:00:00+09:00", run_id="test-only",
    )
    cases = (
        (save_log_csv_batch_state, load_log_csv_batch_state, state),
        (save_log_csv_processing_history, load_log_csv_processing_history, empty_log_csv_processing_history()),
    )
    real_replace = os.replace
    for save, load, payload in cases:
        with tempfile.TemporaryDirectory(prefix="csv-persistence-test-") as directory:
            target = Path(directory) / "state.json"
            gate = Barrier(2)
            temporary_paths = []
            waited = set()

            def simultaneous_replace(source, destination):
                temporary_paths.append(str(source))
                thread_id = get_ident()
                if thread_id not in waited:
                    waited.add(thread_id)
                    gate.wait(timeout=5)
                return real_replace(source, destination)

            with patch("os.replace", side_effect=simultaneous_replace):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    futures = [pool.submit(save, target, payload) for _ in range(2)]
                    errors = [future.exception() for future in futures if future.exception() is not None]
            assert not errors, f"{save.__name__}: simultaneous checkpoints collided: {errors}"
            assert len(set(temporary_paths)) == 2, "Checkpoint writers must not share a temporary file"
            assert load(target) == payload
            assert [path.name for path in target.parent.iterdir()] == ["state.json"]
            print(f"PASS: concurrent atomic checkpoints ({save.__name__})")

            attempts = 0

            def temporary_sharing_violation(source, destination):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    raise PermissionError("Synthetic short-lived Windows sharing violation")
                return real_replace(source, destination)

            with patch("os.replace", side_effect=temporary_sharing_violation):
                save(target, payload)
            assert attempts == 3
            assert load(target) == payload
            print(f"PASS: transient replace error recovered ({save.__name__})")

            with patch("os.replace", side_effect=PermissionError("Synthetic permanent error")):
                try:
                    save(target, payload)
                except PermissionError:
                    pass
                else:
                    raise AssertionError("Permanent checkpoint errors must not be swallowed")
            assert load(target) == payload
            assert [path.name for path in target.parent.iterdir()] == ["state.json"]
            print(f"PASS: old checkpoint survives permanent error ({save.__name__})")


if __name__ == "__main__":
    main()
