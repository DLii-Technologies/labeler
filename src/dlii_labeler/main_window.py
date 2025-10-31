from PyQt6.QtGui import (
	QIcon
)
from PyQt6.QtWidgets import (
	QLabel,
	QMainWindow,
	QMenuBar,
	QStatusBar,
)
from .widget.pane import Pane
from .widget.viewport_widget import ViewportWidget

class MainWindow(QMainWindow):
	def __init__(self):
		super().__init__()

		from .application import Application
		self._app = Application.instance()
		self.setWindowTitle(f"{self._app.applicationName()} v{self._app.applicationVersion()}")
		self.setWindowIcon(QIcon(":/images/icon.png"))
		self.resize(1000, 700)

		self._viewport = Pane()
		self._viewport.setWidget(ViewportWidget())
		self.setCentralWidget(self._viewport)

		self._status_bar = QStatusBar()
		self.setStatusBar(self._status_bar)

		self._menu_bar = QMenuBar()
		self.setMenuBar(self._menu_bar)

		self._populateMenuBar()
		self._populateStatusBar()


	def _populateMenuBar(self):
		from PyQt6.QtGui import QAction, QKeySequence

		file_menu = self._menu_bar.addMenu("&File")
		open_folder_action = QAction("Open Folder", self)
		open_folder_action.setShortcut(QKeySequence("Ctrl+O"))
		open_folder_action.triggered.connect(self.openFolder)
		file_menu.addAction(open_folder_action)
		file_menu.addSeparator()

		export_menu = file_menu.addMenu("&Export")
		export_menu.addAction("YOLO", self._app._exporters["YOLO"].show)
		file_menu.addSeparator()
		file_menu.addAction("Exit", self.close)


	def _populateStatusBar(self):
		index = self._app.mediaManager().index()
		self._status_frames = QLabel(f"Frame: {index + 1} / {self._app.mediaManager().length()}")
		self._status_bar.addPermanentWidget(self._status_frames)
		self._app.mediaManager().frameIndexChanged.connect(self._onFrameChanged)

		self._onFrameChanged(self._app.mediaManager().index())


	def openFolder(self) -> bool:
		return self._app.openFolder(parent=self)


	def _onFrameChanged(self, index: int):
		self._status_frames.setText(f"Frame: {index + 1} / {self._app.mediaManager().length()}")
