"""Tracks the single most recently opened/saved model, across app launches."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class RecentModelStore:
    """Atomically persist the last-opened model's path in a per-user JSON file."""

    filename = ".architecture_model.json"

    def __init__(self, home: Path | None = None) -> None:
        self.home = Path(home) if home is not None else Path.home()

    @property
    def store_path(self) -> Path:
        return self.home / self.filename

    def load(self) -> Path | None:
        if not self.store_path.is_file():
            return None
        try:
            payload = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        last_model_path = payload.get("last_model_path")
        return Path(last_model_path) if last_model_path else None

    def save(self, model_root: Path) -> None:
        destination = self.store_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"last_model_path": str(model_root)}, indent=2) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent, delete=False
        ) as temporary:
            temporary.write(payload)
            temporary_path = Path(temporary.name)
        try:
            os.replace(temporary_path, destination)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise
