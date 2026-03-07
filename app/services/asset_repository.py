import json
import os
from typing import Any, Dict, List, Tuple


class AssetRepository:
    def __init__(self, data_dir: str | None = None) -> None:
        base_dir = data_dir or os.path.join(os.getcwd(), "legacy", "data")
        self.data_dir = base_dir
        self._cache: Dict[str, Any] = {}

    def _file_path(self, filename: str) -> str:
        return os.path.join(self.data_dir, filename)

    def load(self, filename: str) -> Any:
        if filename in self._cache:
            return self._cache[filename]
        path = self._file_path(filename)
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        self._cache[filename] = payload
        return payload

    def reload(self, filename: str) -> Any:
        self._cache.pop(filename, None)
        return self.load(filename)

    def _entry_container(self, filename: str, payload: Any) -> Any:
        # Opponents are grouped under base_opponents; expose that as the primary list.
        if filename == "opponents.json" and isinstance(payload, dict):
            base = payload.get("base_opponents")
            if isinstance(base, dict):
                return base
        return payload

    def entry_labels(self, filename: str) -> List[str]:
        payload = self.load(filename)
        container = self._entry_container(filename, payload)
        if isinstance(container, dict):
            return list(container.keys())
        if isinstance(container, list):
            return [str(i) for i in range(len(container))]
        return []

    def entry(self, filename: str, label: str) -> Tuple[str, Any]:
        payload = self.load(filename)
        container = self._entry_container(filename, payload)
        if isinstance(container, dict):
            return label, container.get(label, {})
        if isinstance(container, list):
            idx = int(label)
            return label, container[idx]
        return label, container

