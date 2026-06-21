"""Lightning event block management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import Database, utc_now_iso


class BlockManager:
    def __init__(self, db: Database, timeout_minutes: int = 5) -> None:
        self.db = db
        self.timeout_minutes = timeout_minutes
        self._current_block_id: int | None = None
        self._last_relevant_ts: datetime | None = None
        self._ensure_block()

    def _ensure_block(self) -> None:
        open_block = self.db.get_open_block()
        if open_block:
            self._current_block_id = int(open_block["id"])
        else:
            self._current_block_id = self.db.create_block()

    def _maybe_rotate_block(self) -> None:
        if self._last_relevant_ts is None:
            return
        if datetime.now(timezone.utc) - self._last_relevant_ts > timedelta(minutes=self.timeout_minutes):
            if self._current_block_id is not None:
                events = self.db.events_in_block(
                    self._current_block_id, relevant_only=True)
                self.db.close_block(self._current_block_id, len(events))
            self._current_block_id = self.db.create_block()
            self._last_relevant_ts = None

    def on_event(self, relevant: bool) -> int | None:
        self._maybe_rotate_block()
        if relevant:
            self._last_relevant_ts = datetime.now(timezone.utc)
        return self._current_block_id

    def current_block_id(self) -> int | None:
        self._maybe_rotate_block()
        return self._current_block_id

    def current_block_summary(self) -> dict[str, Any]:
        block_id = self.current_block_id()
        if block_id is None:
            return {}
        stats = self.db.block_stats(block_id)
        last_rel = self.db.last_relevant_event()
        return {
            **stats,
            "last_relevant": dict(last_rel) if last_rel else None,
        }
