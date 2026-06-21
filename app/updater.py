"""GitHub self-updater with 60-minute measurement deferral."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from app.database import Database

logger = logging.getLogger(__name__)


class Updater:
    def __init__(
        self,
        install_dir: Path,
        db: Database,
        check_interval_hours: float = 6,
        defer_minutes: int = 60,
        on_before_restart: Callable[[str], None] | None = None,
    ) -> None:
        self.install_dir = install_dir
        self.db = db
        self.check_interval_hours = check_interval_hours
        self.defer_minutes = defer_minutes
        self.on_before_restart = on_before_restart
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._next_check = time.monotonic()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="updater")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        interval = self.check_interval_hours * 3600
        while not self._stop.is_set():
            if time.monotonic() >= self._next_check:
                self._check_update()
                self._next_check = time.monotonic() + interval
            self._stop.wait(60)

    def _check_update(self) -> None:
        if self.db.has_relevant_since(self.defer_minutes):
            logger.info(
                "Update deferred: relevant events in last %s min", self.defer_minutes)
            self._next_check = time.monotonic() + self.defer_minutes * 60
            return
        try:
            subprocess.run(
                ["git", "fetch", "origin"],
                cwd=self.install_dir,
                check=True,
                capture_output=True,
                text=True,
            )
            local = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.install_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            remote = subprocess.run(
                ["git", "rev-parse", "origin/main"],
                cwd=self.install_dir,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            if local == remote:
                logger.info("No update available")
                return
            logger.info("Update available: %s -> %s", local[:8], remote[:8])
            subprocess.run(["git", "pull", "origin", "main"],
                           cwd=self.install_dir, check=True)
            venv_python = self.install_dir / ".venv" / "bin" / "python"
            if venv_python.exists():
                subprocess.run(
                    [str(venv_python), "-m", "pip",
                     "install", "-r", "requirements.txt"],
                    cwd=self.install_dir,
                    check=True,
                )
            if self.on_before_restart:
                self.on_before_restart("update")
            self._restart()
        except subprocess.CalledProcessError as exc:
            logger.error("Update failed: %s",
                         exc.stderr if exc.stderr else exc)
        except Exception as exc:
            logger.error("Update error: %s", exc)

    def _restart(self) -> None:
        logger.info("Restarting application after update")
        python = sys.executable
        run_py = self.install_dir / "app" / "run.py"
        os.execv(python, [python, str(run_py)])
