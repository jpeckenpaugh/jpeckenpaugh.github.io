import json
import os
from typing import Any, Dict, List, Tuple


class AssetRepository:
    def __init__(self, data_dir: str | None = None) -> None:
        base_dir = data_dir or os.path.join(os.getcwd(), "legecay", "data")
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

    def entry_labels(self, filename: str) -> List[str]:
        payload = self.load(filename)
        if isinstance(payload, dict):
            return list(payload.keys())
        if isinstance(payload, list):
            return [str(i) for i in range(len(payload))]
        return []

    def entry(self, filename: str, label: str) -> Tuple[str, Any]:
        payload = self.load(filename)
        if isinstance(payload, dict):
            return label, payload.get(label, {})
        if isinstance(payload, list):
            idx = int(label)
            return label, payload[idx]
        return label, payload