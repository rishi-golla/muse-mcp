from __future__ import annotations

from pathlib import Path

from creativity_layer.models import RunResult


class JsonTraceStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, result: RunResult) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{result.run_id}.json"
        path.write_text(
            result.model_dump_json(indent=2),
            encoding="utf-8",
        )
        return path
