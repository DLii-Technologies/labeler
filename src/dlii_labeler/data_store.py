from pathlib import Path
from copy import deepcopy
import dbm
import shelve
from typing import List, Union
from PyQt6.QtCore import QObject, pyqtSignal

from dlii_labeler import __version__

class DataStore(QObject):
	modifiedChanged = pyqtSignal(bool)

	def __init__(self, folder_path: Union[Path, str]):
		super().__init__()
		self._folder_path = Path(folder_path)
		self._store_path = self._folder_path / ".dlii_labels"
		self._data = {}
		self._modified = False
		if dbm.whichdb(str(self._store_path / "data")) is not None:
			with shelve.open(str(self._store_path / "data"), flag="r") as database:
				self._data = dict(database)
		self._data.setdefault("version", __version__)

	def sync(self) -> None:
		"""Write the in-memory project only when Save is requested."""
		self._store_path.mkdir(exist_ok=True)
		with shelve.open(str(self._store_path / "data")) as database:
			database.update(self._data)
			database.sync()
		self.setModified(False)

	def isModified(self) -> bool:
		return self._modified

	def setModified(self, modified: bool) -> None:
		if modified != self._modified:
			self._modified = modified
			self.modifiedChanged.emit(modified)

	def checkVersion(self) -> bool:
		return self._data["version"] == __version__

	def get(self, key: str, default=None):
		return deepcopy(self._data.get(key, default))

	def set(self, key: str, value, *, mark_modified: bool = True) -> None:
		if key not in self._data or self._data[key] != value:
			self._data[key] = deepcopy(value)
			if mark_modified:
				self.setModified(True)

	def images(self) -> List[Path]:
		return [self._folder_path / p for p in self.get("image_paths", [])]

	def setImagePaths(self, image_paths: List[Path]) -> None:
		self.set("image_paths", [str(p.relative_to(self._folder_path)) for p in image_paths])

	def close(self) -> None:
		"""Closing never saves; there is no open database handle to release."""
