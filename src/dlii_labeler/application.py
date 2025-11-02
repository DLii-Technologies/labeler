import json
from pathlib import Path
from typing import Dict, Optional, Union
from PyQt6.QtCore import (
	QFile,
	pyqtSignal
)
from PyQt6.QtGui import (
	QImage,
	QPixmap
)
from PyQt6.QtWidgets import (
	QApplication,
	QFileDialog,
	QMessageBox,
	QWidget
)

from . import gen
from .activity import Activity
from .activity.object_detection_activity import ObjectDetectionActivity
from .data_store import DataStore
from .export.yolo_exporter import YoloExporter
from .media_manager import MediaManager

class Application(QApplication):

	folderOpened = pyqtSignal(str)
	imageChanged = pyqtSignal(QPixmap)

	@classmethod
	def instance(cls) -> "Application":
		return QApplication.instance() # type: ignore

	def __init__(self, argv):
		super().__init__(argv)

		manifest = QFile(":/manifest.json")
		manifest.open(QFile.OpenModeFlag.ReadOnly | QFile.OpenModeFlag.Text)
		manifest_data = manifest.readAll().data().decode("utf-8")
		manifest.close()
		manifest = json.loads(manifest_data)

		self.setApplicationName(manifest["display_name"])
		self.setApplicationVersion(manifest["version"])
		self.setOrganizationName(manifest["organization"])
		self.setOrganizationDomain(manifest["organization_domain"])

		self._media_manager = MediaManager()

		self._activities = {
			Activity.IDENTIFIER: Activity(),
			ObjectDetectionActivity.IDENTIFIER: ObjectDetectionActivity()
		}
		for activity in self._activities.values():
			self.imageChanged.connect(activity.setPixmap)

		self._exporters = {
			YoloExporter.IDENTIFIER: YoloExporter()
		}

		w, h = 1280, 720
		image = QImage(w, h, QImage.Format.Format_RGB32)
		for y in range(h):
			line = (y * 255) // max(1, h - 1)
			for x in range(w):
				r = (x * 255) // max(1, w - 1)
				image.setPixel(x, y, (255 << 24) | (r << 16) | (line << 8) | 32)
		self.setPixmap(QPixmap.fromImage(image))

	def activities(self) -> Dict[str, Activity]:
		return self._activities

	def dataStore(self) -> DataStore:
		return self._data_store

	def mediaManager(self) -> MediaManager:
		return self._media_manager

	def folderPath(self) -> Path:
		return self._folder_path

	def setPixmap(self, image: QPixmap):
		self.imageChanged.emit(image)

	def openFolder(self, folder_path: Optional[Union[Path, str]] = None, parent: Optional[QWidget] = None) -> bool:
		if not folder_path is not None:
			# Open a file dialog to select a folder of images
			current_directory = str(self._media_manager.folder() or "") or None
			folder_path = QFileDialog.getExistingDirectory(parent, "Open Folder", directory=current_directory)
			if not folder_path:
				return False
		self._folder_path = Path(folder_path)
		self._media_manager.setFolder(folder_path)
		self._data_store = DataStore(folder_path)
		self.folderOpened.emit(folder_path)
		if not self.dataStore().checkVersion():
			# Alert the user the data may be incompatible. Ask to continue
			if QMessageBox.warning(
				parent,
				"Warning",
				"Data store version mismatch. Data may be incompatible. Continue?",
				QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
			) == QMessageBox.StandardButton.No:
				self.exit()
				return False
		return True
