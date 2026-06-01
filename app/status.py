import json
from pathlib import Path
from datetime import datetime


def write_status(status_dir: Path, stem: str, status: str, progress: int, message: str = ""):
    status_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "file": stem,
        "status": status,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    path = status_dir / f"{stem}.status.json"
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def read_status_files(status_dir: Path):
    status_dir.mkdir(parents=True, exist_ok=True)

    items = []
    for path in status_dir.glob("*.status.json"):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue

    return sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True)
