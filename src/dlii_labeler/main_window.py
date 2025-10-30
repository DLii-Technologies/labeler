from PyQt6.QtGui import (
    QIcon
)
from PyQt6.QtWidgets import (
	QMainWindow,
    QStatusBar,
)

from .widget.pane import Pane
from .widget.viewport_widget import ViewportWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        from .application import Application
        app = Application.instance()
        self.setWindowTitle(f"{app.applicationName()} v{app.applicationVersion()}")
        self.setWindowIcon(QIcon(":/images/icon.png"))
        self.resize(1000, 700)

        self._viewport = Pane()
        self._viewport.setWidget(ViewportWidget())
        self.setCentralWidget(self._viewport)
        # self._viewport.fitToWindow()

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
