import json
from PyQt6.QtCore import QFile
from PyQt6.QtWidgets import QApplication

from . import gen

class Application(QApplication):

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
