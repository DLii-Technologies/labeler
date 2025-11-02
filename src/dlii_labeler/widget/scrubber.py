
from PyQt6.QtCore import (
	QPoint,
	QRectF,
	Qt
)
from PyQt6.QtGui import (
	QColor,
	QMouseEvent,
	QPainter,
	QWheelEvent
)
from PyQt6.QtWidgets import (
	QGraphicsRectItem,
	QGraphicsScene,
	QGraphicsView,
	QWidget
)

from .pane_widget import PaneWidget

class Scrubber(PaneWidget, QWidget):

	KEYFRAME_SIZE = 16
	TRACK_HEIGHT = 24

	def __init__(self, parent=None):
		super().__init__(parent)

		from ..application import Application
		self._app = Application.instance()

		self._app.mediaManager().folderChanged.connect(self._reset)
		self._app.mediaManager().frameIndexChanged.connect(self._onFrameChanged)

		self.setMinimumHeight(48)

		self._reset()


	def _reset(self):
		"""
		Reconfigure the timeline.
		"""
		# self.scene().clear()
		# self.setSceneRect(0, 0, self.length(), self.scene().sceneRect().height())
		# self.scale()


	def _updateBaseTransform(self):
		...


	def _onFrameChanged(self, index: int):
		# Update the scrubber position
		self.repaint()


	def paintEvent(self, painterEvent: QPaintEvent):
		"""
		TODO:
		One scene unit = 1 frame.
		At the top, draw a gray background with frame markers spaced evenly.
		The resolution of the frame markers depends on the zoom level.
		They should step by 1, then 2, then 5, then 10, and repeat for increasing magnitudes
		(i.e. 10, 20, 50, 100, 200, 500, 1000, etc.).
		The frame resolution decreases as we zoom out and increases as we zoom in. It needs to pick
		an appropriate resolution such that the markers are guaranteed to not overlap.

		After determining the frame markers, draw a dark gray vertical line spanning the scene
		(below the frame marker bar). Draw an intermediate gray (50% between dark gray and background)
		marker perfectly centered between each dark gray marker unless we're at 1-frame resolution.
		"""
		painter = QPainter(self)

		width = self.width()
		height = self.height()
		pos = (self.currentFrame() / self.length() * width)

		rect = QRectF(pos, 0, 1, height).adjusted(-0.5, 0.0, 0.0, 0.0)

		painter.fillRect(rect, Qt.GlobalColor.blue)


	def mousePressEvent(self, event: QMouseEvent) -> None:
		if event.button() == Qt.MouseButton.LeftButton:
			pos = event.position().toPoint()
			if pos.x() < 0 or pos.x() >= self.width():
				return
			frame = int(pos.x() / self.width() * self.length())
			self.setFrame(frame)
			event.accept()
			return
		super().mousePressEvent(event)


	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		if event.buttons() & Qt.MouseButton.LeftButton:
			pos = event.position().toPoint()
			if pos.x() < 0 or pos.x() >= self.width():
				return
			frame = int(pos.x() / self.width() * self.length())
			self.setFrame(frame)
			event.accept()
			return
		super().mouseMoveEvent(event)


	def currentFrame(self) -> int:
		"""
		Get the current frame index
		"""
		return self._app.mediaManager().index()


	def setFrame(self, index: int) -> None:
		"""
		Set the current frame index
		"""
		self._app.mediaManager().setIndex(index)
		self.update()


	def length(self) -> int:
		"""
		Get the total number of frames
		"""
		return self._app.mediaManager().length()
