from PyQt6.QtCore import (
	QByteArray,
	QEvent,
	QRect,
	Qt
)
from PyQt6.QtGui import (
	QIcon
)
from PyQt6.QtWidgets import (
	QDockWidget,
	QLabel,
	QMainWindow,
	QMenuBar,
	QStatusBar,
)
from .widget.pane import Pane
from .widget.object_properties_widget import ObjectPropertiesWidget
from .widget.scrubber import Scrubber
from .widget.viewport_widget import ViewportWidget
from .widget.label_set_manager import LabelSetManagerDialog

class MainWindow(QMainWindow):
	WINDOW_DATA_KEY = "main_window_state"

	def __init__(self):
		super().__init__()
		self._restoring_window_state = True

		from .application import Application
		self._app = Application.instance()
		self._app.folderOpened.connect(self._restoreWindowState)
		self.setWindowTitle(f"{self._app.applicationName()} v{self._app.applicationVersion()}")
		self.setWindowIcon(QIcon(":/images/icon.png"))
		self.resize(1000, 700)

		self._viewport = Pane()
		self._viewport_widget = ViewportWidget()
		self._viewport.setWidget(self._viewport_widget)
		self.setCentralWidget(self._viewport)

		self._scrubber = Scrubber()
		self._scrubber_dock = QDockWidget("Scrubber", self)
		self._scrubber_dock.setObjectName("scrubber_dock")
		self._scrubber_dock.setWidget(self._scrubber)
		self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._scrubber_dock)

		self._object_properties = ObjectPropertiesWidget()
		self._object_properties.setMinimumSize(0, 0)
		self._properties_dock = QDockWidget("Properties", self)
		self._properties_dock.setObjectName("properties_dock")
		self._properties_dock.setMinimumSize(0, 0)
		self._properties_dock.setWidget(self._object_properties)
		self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._properties_dock)
		self._viewport_widget.activityChanged.connect(self._object_properties.setActivity)
		self._object_properties.setActivity(self._viewport_widget.activity())
		for dock in (self._scrubber_dock, self._properties_dock):
			dock.dockLocationChanged.connect(self._saveWindowState)
			dock.topLevelChanged.connect(self._saveWindowState)
			dock.visibilityChanged.connect(self._saveWindowState)

		self._status_bar = QStatusBar()
		self.setStatusBar(self._status_bar)

		self._menu_bar = QMenuBar()
		self.setMenuBar(self._menu_bar)

		self._populateMenuBar()
		self._populateStatusBar()
		self._restoreWindowState()

		self._app.mediaManager().folderChanged.connect(self.updateTitle)


	def _restoreWindowState(self, *_args) -> None:
		self._restoring_window_state = True
		try:
			data_store = self._app.dataStore()
			window_data = data_store.get(self.WINDOW_DATA_KEY) if data_store is not None else None
			self.setWindowState(Qt.WindowState.WindowNoState)
			if isinstance(window_data, dict):
				geometry = window_data.get("geometry")
				if isinstance(geometry, dict):
					self._restoreNormalizedGeometry(geometry)
				elif isinstance(geometry, (bytes, bytearray)):
					# Migrate projects that still contain the old absolute geometry format.
					self.restoreGeometry(QByteArray(bytes(geometry)))
					if not self.isMaximized() and not self.isFullScreen():
						self._constrainGeometryToScreen()

				state = window_data.get("state")
				if isinstance(state, (bytes, bytearray)):
					self.restoreState(QByteArray(bytes(state)))

				if window_data.get("fullscreen", False):
					self.setWindowState(Qt.WindowState.WindowFullScreen)
				elif window_data.get("maximized", False):
					self.setWindowState(Qt.WindowState.WindowMaximized)
		finally:
			self._restoring_window_state = False
			self._saveWindowState()


	def _screenGeometry(self) -> QRect:
		screen = self.screen() or self._app.primaryScreen()
		return screen.availableGeometry() if screen is not None else QRect()


	def _restoreNormalizedGeometry(self, geometry_data: dict) -> bool:
		screen_geometry = self._screenGeometry()
		values = tuple(geometry_data.get(key) for key in ("x", "y", "width", "height"))
		if not screen_geometry.isValid() or not all(
			isinstance(value, (int, float)) for value in values
		):
			return False

		x_ratio, y_ratio, width_ratio, height_ratio = values
		width = min(screen_geometry.width(), max(1, round(width_ratio * screen_geometry.width())))
		height = min(screen_geometry.height(), max(1, round(height_ratio * screen_geometry.height())))
		x = round(screen_geometry.x() + x_ratio * screen_geometry.width())
		y = round(screen_geometry.y() + y_ratio * screen_geometry.height())

		max_x = screen_geometry.x() + screen_geometry.width() - width
		max_y = screen_geometry.y() + screen_geometry.height() - height
		x = min(max(screen_geometry.x(), x), max_x)
		y = min(max(screen_geometry.y(), y), max_y)
		self.setGeometry(QRect(x, y, width, height))
		return True


	def _constrainGeometryToScreen(self) -> None:
		screen_geometry = self._screenGeometry()
		if not screen_geometry.isValid():
			return
		geometry = self.geometry()
		width = min(screen_geometry.width(), max(1, geometry.width()))
		height = min(screen_geometry.height(), max(1, geometry.height()))
		x = min(
			max(screen_geometry.x(), geometry.x()),
			screen_geometry.x() + screen_geometry.width() - width,
		)
		y = min(
			max(screen_geometry.y(), geometry.y()),
			screen_geometry.y() + screen_geometry.height() - height,
		)
		self.setGeometry(QRect(x, y, width, height))


	def _normalizedGeometry(self) -> dict | None:
		screen_geometry = self._screenGeometry()
		if not screen_geometry.isValid():
			return None

		geometry = self.normalGeometry() if self.isMaximized() or self.isFullScreen() else self.geometry()
		if geometry.isNull():
			geometry = self.geometry()
		return {
			"x": (geometry.x() - screen_geometry.x()) / screen_geometry.width(),
			"y": (geometry.y() - screen_geometry.y()) / screen_geometry.height(),
			"width": geometry.width() / screen_geometry.width(),
			"height": geometry.height() / screen_geometry.height(),
		}


	def _saveWindowState(self, *_args) -> None:
		if getattr(self, "_restoring_window_state", True):
			return
		app = getattr(self, "_app", None)
		data_store = app.dataStore() if app is not None else None
		if data_store is None:
			return
		normalized_geometry = self._normalizedGeometry()
		if normalized_geometry is None:
			return
		data_store.set(self.WINDOW_DATA_KEY, {
			"geometry": normalized_geometry,
			"state": bytes(self.saveState()),
			"maximized": self.isMaximized(),
			"fullscreen": self.isFullScreen(),
		})


	def resizeEvent(self, event) -> None:
		super().resizeEvent(event)
		self._saveWindowState()


	def moveEvent(self, event) -> None:
		super().moveEvent(event)
		self._saveWindowState()


	def changeEvent(self, event) -> None:
		super().changeEvent(event)
		if event.type() == QEvent.Type.WindowStateChange:
			self._saveWindowState()


	def closeEvent(self, event) -> None:
		self._saveWindowState()
		super().closeEvent(event)


	def _populateMenuBar(self):
		from PyQt6.QtGui import QAction, QKeySequence

		file_menu = self._menu_bar.addMenu("&File")
		open_folder_action = QAction("Open Folder", self)
		open_folder_action.setShortcut(QKeySequence("Ctrl+O"))
		open_folder_action.triggered.connect(self.openFolder)
		file_menu.addAction(open_folder_action)
		file_menu.addSeparator()

		export_menu = file_menu.addMenu("&Export")
		for exporter_name, exporter in self._app._exporters.items():
			export_menu.addAction(exporter_name, exporter.show)
		file_menu.addSeparator()
		file_menu.addAction("Exit", self.close)

		view_menu = self._menu_bar.addMenu("&View")
		view_menu.addAction(self._properties_dock.toggleViewAction())
		view_menu.addAction(self._scrubber_dock.toggleViewAction())

		labels_menu = self._menu_bar.addMenu("&Labels")
		labels_menu.addAction("Manage Label Sets...", self._showLabelSetManager)


	def _showLabelSetManager(self) -> None:
		dialog = LabelSetManagerDialog(self)
		dialog.exec()


	def _populateStatusBar(self):
		index = self._app.mediaManager().index()
		self._status_frames = QLabel(f"Frame: {index + 1} / {self._app.mediaManager().length()}")
		self._status_bar.addPermanentWidget(self._status_frames)
		self._app.mediaManager().frameIndexChanged.connect(self._onFrameChanged)

		self._onFrameChanged(self._app.mediaManager().index())


	def _onFrameChanged(self, index: int):
		self._status_frames.setText(f"Frame: {index + 1} / {self._app.mediaManager().length()}")


	def updateTitle(self):
		path = self._app.mediaManager().folder()
		title = f"{self._app.applicationName()} v{self._app.applicationVersion()}"
		if path is not None:
			title += f" - {path}"
		self.setWindowTitle(title)


	def openFolder(self) -> bool:
		return self._app.openFolder(parent=self)
