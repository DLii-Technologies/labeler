from pathlib import Path
import shelve
from typing import List, Union

from . import __version__

class DataStore:
	def __init__(self, folder_path: Union[Path, str]):
		self._folder_path = Path(folder_path)
		self._store_path = self._folder_path / ".dlii_labels"
		self._store_path.mkdir(exist_ok=True)
		self._db = shelve.open(self._store_path / "data", writeback=True)

		if "version" not in self._db:
			self._db["version"] = __version__
			self.sync()

	def sync(self) -> None:
		self._db.close()
		self._db = shelve.open(self._store_path / "data", writeback=True)

	def checkVersion(self) -> bool:
		if "version" not in self._db:
			self._db["version"] = __version__
			self.sync()
		return self._db["version"] == __version__

	def get(self, key: str):
		return self._db.get(key, None)

	def set(self, key: str, value) -> None:
		self._db[key] = value
		self.sync()

	def images(self) -> List[Path]:
		return [self._folder_path / p for p in self.get("image_paths", [])]

	def setImagePaths(self, image_paths: List[Path]) -> None:
		self.set("image_paths", [str(p.relative_to(self._folder_path)) for p in image_paths])

	def close(self) -> None:
		self._db.close()

	def __del__(self):
		self.close()
