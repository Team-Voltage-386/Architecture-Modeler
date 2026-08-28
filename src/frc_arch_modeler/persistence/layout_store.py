"""Persistence for user-specific architecture canvas presentation."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class LayoutStore:
    """Read and atomically replace ``.frc-architecture/layout.json``."""

    directory_name = ".frc-architecture"
    layout_filename = "layout.json"
    schema_version = 1

    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def layout_path(self) -> Path:
        return self.root / self.directory_name / self.layout_filename

    def save(
        self, layout: dict[str, dict[str, Any]], ui: dict[str, Any] | None = None
    ) -> Path:
        destination = self.layout_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"schemaVersion": self.schema_version, "elements": layout, "ui": ui or {}},
            indent=2,
            ensure_ascii=False,
        ) + "\n"
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
        return destination

    def load(self) -> dict[str, dict[str, Any]]:
        return self._load_payload()["elements"]

    def load_ui(self) -> dict[str, Any]:
        """Return optional non-semantic window/panel preferences."""
        return self._load_payload().get("ui", {})

    def _load_payload(self) -> dict[str, Any]:
        if not self.layout_path.exists():
            return {"elements": {}, "ui": {}}
        with self.layout_path.open(encoding="utf-8") as layout_file:
            payload = json.load(layout_file)
        if payload.get("schemaVersion") != self.schema_version:
            raise ValueError("Unsupported layout schema version.")
        elements = payload.get("elements", {})
        if not isinstance(elements, dict):
            raise ValueError("Layout elements must be an object.")
        ui = payload.get("ui", {})
        if not isinstance(ui, dict):
            raise ValueError("Layout UI preferences must be an object.")
        return {"elements": elements, "ui": ui}
