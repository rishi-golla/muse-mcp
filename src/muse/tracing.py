from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from muse.models import RunResult
from muse.privacy import TraceView


class JsonTraceStore:
    def __init__(self, root: Path, *, trace_view: TraceView | None = None) -> None:
        self._root = root
        self._trace_view = trace_view or TraceView()

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
                payload = result.model_dump(mode="json")
                sanitized = self._trace_view.sanitize(payload)
                temp_file.write(json.dumps(sanitized, indent=2))
                temp_file.flush()
                os.fsync(temp_file.fileno())

            os.replace(temp_path, path)
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return path
