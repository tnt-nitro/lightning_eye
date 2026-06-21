"""Boot reason persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def boot_file(data_dir: Path) -> Path:
    return data_dir / "last_boot.json"


def write_boot_reason(data_dir: Path, reason: str, extra: dict[str, Any] | None = None) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "reason": reason,
        "ts": datetime.now(timezone.utc).isoformat(),
        **(extra or {}),
    }
    boot_file(data_dir).write_text(
        json.dumps(payload, indent=2), encoding="utf-8")


def read_boot_reason(data_dir: Path) -> dict[str, Any]:
    path = boot_file(data_dir)
    if not path.exists():
        return {"reason": "unknown", "ts": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"reason": "unknown", "ts": None}
