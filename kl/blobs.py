"""Where file bytes and artifacts live: content-addressed, so the same bytes are stored once.

LocalBlobs keeps them under the data folder. A hosted deployment swaps in an
object store with the same three methods; nothing else touches the files.
"""
from pathlib import Path

from . import ids


class LocalBlobs:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / key

    def put(self, data: bytes) -> str:
        key = ids.sha256(data)
        path = self._path(key)
        if not path.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def has(self, key: str) -> bool:
        return self._path(key).is_file()
