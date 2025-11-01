from functools import lru_cache
from pathlib import Path
from typing import Callable, List, Optional, Union
from PyQt6.QtCore import (
	pyqtSignal,
	QObject,
	QRunnable,
	QThreadPool
)
from PyQt6.QtGui import (
	QPixmap
)

# class _ImageLoadtask(QRunnable):
# 	def __init__(self, index: int, path: Path, request_id: int, callback: Callable[[int, QPixmap, int], None]):
# 		super().__init__()
# 		self.index = index
# 		self.path = path
# 		self.request_id = request_id
# 		self.callback = callback

# 	def run(self):
# 		self.callback(self.index, QPixmap(str(self.path)), self.request_id)

class MediaManager(QObject):
	"""
	Handles loading of various media types:
	- Single images (PNG, JPG, BMP, TIFF)
	- Video files (MP4, AVI, MOV, etc.)
	- Folders of images
	"""

	folderChanged = pyqtSignal(str)
	frameIndexChanged = pyqtSignal(int)
	frameChanged = pyqtSignal(QPixmap)

	SUPPORTED_IMAGE_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'}
	# SUPPORTED_VIDEO_FORMATS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm'}

	def __init__(self):
		super().__init__()
		self._current_frame = QPixmap()
		self._image_paths: List[Path] = []
		self._current_index = 0

		# Threading
		self._pool = QThreadPool.globalInstance()
		self._latest_request_id = 0


	def index(self):
		return self._current_index


	def length(self):
		return len(self._image_paths)


	def scanFolder(self, folder_path: Union[Path, str]):
		image_paths = []
		for file in Path(folder_path).iterdir():
			if file.suffix.lower() in self.SUPPORTED_IMAGE_FORMATS:
				image_paths.append(file)
		return sorted(image_paths)


	def setFolder(self, folder_path: Union[Path, str], image_paths: Optional[List[Path]] = None) -> Optional[List[str]]:
		# Find all image files in folder
		if image_paths is None:
			image_paths = self.scanFolder(folder_path)
		self._image_paths = image_paths
		self.folderChanged.emit(folder_path)
		self._current_index = -1
		self.setIndex(0)


	def setIndex(self, index: int) -> None:
		assert 0 <= index < len(self._image_paths)
		if index == self._current_index:
			return
		self._current_index = index
		self._current_frame = self._loadImage(self._image_paths[self._current_index])
		self.frameIndexChanged.emit(self._current_index)
		self.frameChanged.emit(self._current_frame)


	def currentFrame(self) -> QPixmap:
		return self._current_frame


	def currentFrameIndex(self) -> int:
		return self._current_index


	def frame(self, index: int) -> QPixmap:
		return self._loadImage(self._image_paths[index])


	def imagePaths(self) -> List[Path]:
		return self._image_paths


	@lru_cache(maxsize=128)
	def _loadImage(self, path: Path):
		if not path.exists():
			return QPixmap()
		return QPixmap(str(path))
