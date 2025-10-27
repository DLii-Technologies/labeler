from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMainWindow

from .widget.viewport_widget import ViewportWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        from .application import Application
        app = Application.instance()
        self.setWindowTitle(f"{app.applicationName()} v{app.applicationVersion()}")
        self.setWindowIcon(QIcon(":/images/icon.png"))
        self.resize(1000, 700)

        self.viewport = ViewportWidget()
        from PyQt6.QtGui import QImage
        w, h = 1280, 720
        image = QImage(w, h, QImage.Format.Format_RGB32)
        for y in range(h):
            line = (y * 255) // max(1, h - 1)
            for x in range(w):
                r = (x * 255) // max(1, w - 1)
                image.setPixel(x, y, (255 << 24) | (r << 16) | (line << 8) | 32)
        self.viewport.setImage(image)
        self.setCentralWidget(self.viewport)
