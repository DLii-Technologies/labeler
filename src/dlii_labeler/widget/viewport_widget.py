from typing import Optional

from PyQt6.QtCore import (
	QElapsedTimer,
	QPoint,
	QPointF,
	Qt,
	QTimer
)

from PyQt6.QtGui import (
	QCursor,
	QImage,
	QMouseEvent,
	QPixmap,
	QResizeEvent,
	QWheelEvent
)

from PyQt6.QtWidgets import (
	QGraphicsScene,
	QGraphicsView,
	QWidget
)

class ViewportWidget(QGraphicsView):

	ANIM_HALF_LIFE_MS = 45

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)

		# Disable scrollbars
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

		scene = QGraphicsScene(self)
		self.setScene(scene)

		# Panning
		self._pan_anchor_scene_pos: Optional[QPointF] = None

		# Zooming
		self._target_zoom = 1.0
		self._current_zoom = 1.0
		self._zoom_scene_pos: Optional[QPointF] = None # The position in the scene to zoom into

		self._render_step_timer = QTimer(self)
		self._render_step_timer.setTimerType(Qt.TimerType.PreciseTimer)
		self._render_step_timer.setInterval(16)  # ~60Hz
		self._render_step_timer.timeout.connect(self._renderStep)
		self._render_step_elapsed_timer = QElapsedTimer()

	# Public Interface -----------------------------------------------------------------------------

	def isPanning(self) -> bool:
		return self.isMousePanning()


	def isMousePanning(self) -> bool:
		return self._pan_anchor_scene_pos is not None


	def panTo(self, scene_pos: QPointF) -> None:
		# self._zoom_scene_pos = scene_pos
		self._target_pan_pos = scene_pos
		self.scheduleRenderUpdates()


	def setImage(self, image: QImage) -> None:
		scene = self.scene()
		if scene is None:
			return
		self._image = QPixmap.fromImage(image)
		scene.clear()
		scene.addPixmap(self._image)
		self._updateSceneRect()


	def setZoom(self, zoom: float):
		if abs(zoom - self._target_zoom) / max(self._target_zoom, 1e-12) < 1e-6:
			return
		self._target_zoom = zoom
		self.scheduleRenderUpdates()

	# Event Handling -------------------------------------------------------------------------------

	def resizeEvent(self, event: QResizeEvent) -> None:
		super().resizeEvent(event)
		self._updateSceneRect()


	def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
		pos = event.pos()
		if pos is not None:
			self.panTo(self.mapToScene(pos))
		super().mouseDoubleClickEvent(event)


	def mousePressEvent(self, event: QMouseEvent) -> None:
		pos = event.pos()
		if pos is not None:
			# Check for panning
			if event.button() == Qt.MouseButton.MiddleButton or (
				event.button() == Qt.MouseButton.LeftButton and
				(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
			):
				self._pan_anchor_scene_pos = self.mapToScene(pos)
				self.setCursor(Qt.CursorShape.ClosedHandCursor)

		super().mousePressEvent(event)


	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		pos = event.pos()
		if pos is not None and self._pan_anchor_scene_pos is not None:
			# Panning
			delta = pos - self.mapFromScene(self._pan_anchor_scene_pos)
			self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
			self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
			return
		super().mouseMoveEvent(event)


	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		if self._pan_anchor_scene_pos is not None and event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
			self._pan_anchor_scene_pos = None
			self.unsetCursor()
		return super().mouseReleaseEvent(event)


	def wheelEvent(self, event: QWheelEvent) -> None:
		delta = event.angleDelta().y()
		if delta == 0:
			return
		zoom_factor = 1.0015 ** delta
		self._zoom_scene_pos = None
		self.setZoom(self._target_zoom*zoom_factor)

	# Internal -------------------------------------------------------------------------------------

	def scale(self, factor: float) -> None:
		self._current_zoom *= factor
		super().scale(factor, factor)
		self._updateSceneRect()


	def _updateSceneRect(self):
		"""
		Ensures the scene rect is large enough so that we can pan.

		This method should be invoked whenever the image size, window size, or zoom level changes.
		"""
		scene = self.scene()
		if scene is None:
			return
		margin_width = self.width() / self._current_zoom
		margin_height = self.height() / self._current_zoom
		scene.setSceneRect(
			-margin_width,
			-margin_height,
			self._image.width() + 2*margin_width,
			self._image.height() + 2*margin_height
		)

	# Rendering ------------------------------------------------------------------------------------

	def scheduleRenderUpdates(self):
		if not self._render_step_timer.isActive():
			self._render_step_timer.start()
			self._render_step_elapsed_timer.start()


	def _renderStep(self):
		updated = False
		updated |= self._renderStepZoom(self._render_step_elapsed_timer.elapsed())
		updated |= self._renderStepPan(self._render_step_elapsed_timer.elapsed())
		self._render_step_elapsed_timer.restart()
		if not updated:
			self._render_step_timer.stop()
			self._render_step_elapsed_timer.invalidate()


	def _renderStepZoom(self, dt: int):
		if abs(self._target_zoom - self._current_zoom) / max(self._target_zoom, 1e-12) < 1e-3:
			self._zoom_scene_pos = None
			return False

		# Compute zoom factor and new scale
		alpha = 1.0 - pow(0.5, dt/self.ANIM_HALF_LIFE_MS)
		new_scale = (1.0 - alpha) * self._current_zoom + alpha * self._target_zoom
		factor = new_scale / self._current_zoom
		self._current_zoom = new_scale

		# Determine the current zoom position.
		if self._zoom_scene_pos is not None:
			view_pos = self.mapFromScene(self._zoom_scene_pos)
			scene_pos = self._zoom_scene_pos
		elif self.rect().contains(cursor_pos := self.mapFromGlobal(QCursor.pos())):
			view_pos = cursor_pos
			scene_pos = self.mapToScene(view_pos)
		else:
			# No zoom position set, and cursor position is not available
			view_pos = self.rect().center()
			scene_pos = self.mapToScene(view_pos)

		# Update the scene rectangle
		self.scale(factor)

		# Reposition under mouse cursor
		delta = self.mapFromScene(scene_pos) - view_pos
		self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
		self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())

		return True


	def _renderStepPan(self, dt: int):
		return False
