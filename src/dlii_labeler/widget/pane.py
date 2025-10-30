from PyQt6.QtWidgets import (
	QToolBar,
	QVBoxLayout,
	QWidget
)

from .pane_widget import PaneWidget

class Pane(QWidget):
	def __init__(self, parent = None):
		super().__init__(parent)

		self.toolbar = QToolBar()
		layout = QVBoxLayout()
		layout.setContentsMargins(0, 0, 0, 0)
		layout.addWidget(self.toolbar)
		self.setLayout(layout)

	def setWidget(self, widget: PaneWidget):
		self._widget = widget
		widget.setupToolBar(self.toolbar)
		self.layout().addWidget(self._widget) # type: ignore
