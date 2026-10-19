from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

try:
    from send2trash import send2trash
except Exception:  # pragma: no cover - this script is intentionally conservative.
    send2trash = None


PROJECT_DIR = Path(__file__).resolve().parents[1]
DESKTOP_DIR = Path.home() / "OneDrive" / "Desktop"
BACKUP_ROOT = DESKTOP_DIR / "counsel-note_BACKUPS"
KEEP_LATEST = 5
BACKUP_ITEMS = ["app.py", "requirements.txt", "README.md", "prompts", "scripts"]


def copy_item(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    if source.is_dir():
        shutil.copytree(source, destination / source.name, dirs_exist_ok=True)
        return
    shutil.copy2(source, destination / source.name)


def move_old_backups_to_trash() -> list[Path]:
    if send2trash is None:
        return []

    backups = sorted(
        [path for path in BACKUP_ROOT.iterdir() if path.is_dir() and path.name.startswith("counsel-note_BACKUP_")],
        key=lambda path: path.name,
        reverse=True,
    )
    moved: list[Path] = []
    for old_backup in backups[KEEP_LATEST:]:
        send2trash(str(old_backup))
        moved.append(old_backup)
    return moved


def main() -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_ROOT / f"counsel-note_BACKUP_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for item in BACKUP_ITEMS:
        copy_item(PROJECT_DIR / item, backup_dir)

    moved = move_old_backups_to_trash()
    print(f"backup_dir={backup_dir}")
    print(f"trashed_old_backups={len(moved)}")
    if send2trash is None:
        print("warning=send2trash를 사용할 수 없어 오래된 백업을 정리하지 않았습니다.")


if __name__ == "__main__":
    main()
