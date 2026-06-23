from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from creativity_layer.models import RunResult


class JsonTraceStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def save(self, result: RunResult) -> Path:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{result.run_id}.json"
        temp_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._root,
                prefix=f".{result.run_id}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(result.model_dump_json(indent=2))
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return path
