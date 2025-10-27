from typing import Optional

from PyQt6.QtCore import (
	QElapsedTimer,
	QPoint,
	QPointF,
	Qt,
	QTimer
)

from PyQt6.QtGui import (
	QImage,
	QMouseEvent,
	QPixmap,
	QWheelEvent
)

from PyQt6.QtWidgets import (
	QGraphicsScene,
	QGraphicsView,
	QWidget
)

class ViewportWidget(QGraphicsView):
	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)

		# Disable scrollbars
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

		scene = QGraphicsScene(self)
		self.setScene(scene)

		# Panning
		self._last_mouse_pos: QPoint = QPoint(0, 0)
		self._is_panning = False

		# Zooming
		self._zoom_pos = None
		self._target_scale = 1.0
		self._current_scale = 1.0
		self._zoom_half_life_ms = 45

		self._render_step_timer = QTimer(self)
		self._render_step_timer.setTimerType(Qt.TimerType.PreciseTimer)
		self._render_step_timer.setInterval(8)  # ~60Hz
		self._render_step_timer.timeout.connect(self._renderStep)
		self._render_step_elapsed_timer = QElapsedTimer()

	def setImage(self, image: QImage) -> None:
		self._image = QPixmap.fromImage(image)
		self.scene().clear()
		self.scene().addPixmap(self._image)
		self._updateSceneRect()

	def setScale(self, scale, scene_pos: QPointF, view_pos: QPoint):
		if abs(scale - self._target_scale) / max(self._target_scale, 1e-12) < 1e-6:
			return
		self._target_scale = scale
		self._zoom_focus_scene_pos = QPointF(scene_pos)
		self._zoom_focus_view_pos = QPoint(view_pos)
		if not self._render_step_timer.isActive():
			self._render_step_timer.start()
			self._render_step_elapsed_timer.start()

	def resizeEvent(self, event) -> None:
		super().resizeEvent(event)
		self._updateSceneRect()

	def mousePressEvent(self, event: QMouseEvent) -> None:
		self._last_mouse_pos = event.pos()

		print(event.modifiers())

		# Check for panning
		if event.button() == Qt.MouseButton.MiddleButton or (
			event.button() == Qt.MouseButton.LeftButton and
			(event.modifiers() & Qt.KeyboardModifier.AltModifier)
		):
			self._is_panning = True
			self.setCursor(Qt.CursorShape.ClosedHandCursor)

		super().mousePressEvent(event)

	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		if self._is_panning:
			delta = event.pos() - self._last_mouse_pos
			self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
			self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
			self._last_mouse_pos = event.pos()
			return
		super().mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		if self._is_panning and event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
			self._is_panning = False
			self.unsetCursor()

		return super().mouseReleaseEvent(event)

	def wheelEvent(self, event: QWheelEvent) -> None:
		delta = event.angleDelta().y()
		if delta == 0:
			return
		zoom_factor = 1.0015 ** delta
		view_pos = event.position().toPoint()
		scene_pos = self.mapToScene(view_pos)
		self.setScale(self._target_scale*zoom_factor, scene_pos, view_pos)

	def _renderStepZoom(self, dt: float):
		if abs(self._target_scale - self._current_scale) / max(self._target_scale, 1e-12) < 1e-3:
			return False

		alpha = 1.0 - pow(0.5, max(dt, 0.0) / max(self._zoom_half_life_ms, 1e-6))
		new_scale = (1.0 - alpha) * self._current_scale + alpha * self._target_scale
		factor = new_scale / self._current_scale
		if abs(factor - 1.0) < 1e-6:
			return False

		self._current_scale = new_scale

		self.scale(factor, factor)

		# Margin in pixels
		self._updateSceneRect()

		post = self.mapFromScene(self._zoom_focus_scene_pos)
		delta = post - self._zoom_focus_view_pos
		self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
		self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())

		return True

	def _renderStep(self):
		updated = False
		updated |= self._renderStepZoom(self._render_step_elapsed_timer.elapsed())

		self._render_step_elapsed_timer.restart()
		if not updated:
			self._render_step_timer.stop()
			self._render_step_elapsed_timer.invalidate()

	def _updateSceneRect(self):
		"""
		Ensures the scene rect is large enough so that we can pan.
		"""
		margin_width = self.viewport().width() / self._current_scale
		margin_height = self.viewport().height() / self._current_scale
		self.scene().setSceneRect(
			-margin_width,
			-margin_height,
			self._image.width() + 2*margin_width,
			self._image.height() + 2*margin_height
		)
