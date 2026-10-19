from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Callable


class CsvRunBusyError(RuntimeError):
    pass


class CsvRunLease:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a+b")
        try:
            if path.stat().st_size == 0:
                self.stream.write(b"0")
                self.stream.flush()
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.stream.close()
            raise CsvRunBusyError("CSV 저장 작업이 이미 실행 중입니다.") from exc

    def close(self) -> None:
        if self.stream.closed:
            return
        try:
            self.stream.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def csv_worker_is_running(lock_path: Path) -> bool:
    if not lock_path.is_file():
        return False
    try:
        with CsvRunLease(lock_path):
            return False
    except CsvRunBusyError:
        return True


def start_csv_worker(
    lock_path: Path,
    work: Callable[[], None],
    on_error: Callable[[BaseException], None],
) -> threading.Thread:
    lease = CsvRunLease(lock_path)

    def run() -> None:
        try:
            work()
        except BaseException as exc:
            on_error(exc)
        finally:
            lease.close()

    thread = threading.Thread(target=run, name="connect-log-csv-save", daemon=True)
    try:
        thread.start()
    except BaseException:
        lease.close()
        raise
    return thread
