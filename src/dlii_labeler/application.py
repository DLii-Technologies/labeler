import json
from PyQt6.QtCore import (
	QFile,
	pyqtSignal
)
from PyQt6.QtGui import (
	QImage,
	QPixmap
)
from PyQt6.QtWidgets import QApplication

from . import gen
from .activity import Activity
from .activity.object_detection_activity import ObjectDetectionActivity

class Application(QApplication):

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

		self._activities = {
			Activity.IDENTIFIER: Activity(),
			ObjectDetectionActivity.IDENTIFIER: ObjectDetectionActivity()
		}

		for activity in self._activities.values():
			self.imageChanged.connect(activity.setPixmap)

		w, h = 1280, 720
		image = QImage(w, h, QImage.Format.Format_RGB32)
		for y in range(h):
			line = (y * 255) // max(1, h - 1)
			for x in range(w):
				r = (x * 255) // max(1, w - 1)
				image.setPixel(x, y, (255 << 24) | (r << 16) | (line << 8) | 32)
		self.setPixmap(QPixmap.fromImage(image))

	def activities(self):
		return self._activities

	def setPixmap(self, image: QPixmap):
		self.imageChanged.emit(image)
