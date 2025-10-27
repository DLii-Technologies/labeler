from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        from .application import Application
        app = Application.instance()
        self.setWindowTitle(f"{app.applicationName()} v{app.applicationVersion()}")
        self.setWindowIcon(QIcon(":/images/icon.png"))
        self.resize(1000, 700)
