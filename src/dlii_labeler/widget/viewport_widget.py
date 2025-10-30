from typing import Optional
from PyQt6.QtCore import (
	pyqtSignal,
	QElapsedTimer,
	QPoint,
	QPointF,
	QRectF,
	QSize,
	Qt,
	QTimer
)
from PyQt6.QtGui import (
	QAction,
	QCursor,
	QKeyEvent,
	QMouseEvent,
	QResizeEvent,
	QTransform,
	QWheelEvent
)
from PyQt6.QtWidgets import (
	QGraphicsView,
	QMenu,
	QToolBar,
	QToolButton,
	QWidget
)

from ..activity import Activity
from .pane_widget import PaneWidget

class ViewportWidget(PaneWidget, QGraphicsView):

	ZOOM_ANIMATION_HALF_LIFE_MS = 45
	PAN_ANIMATION_HALF_LIFE_MS = 1000

	activityChanged = pyqtSignal(Activity)

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)

		# self.setAlignment(Qt.AlignmentFlag.AlignAbsolute)
		self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

		# Anchoring
		self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
		self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)

		# Disable scrollbars
		self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

		# Set scene rect to infinite
		# self.setSceneRect(-float("inf"), -float("inf"), float("inf"), float("inf"))
		self.setSceneRect(-1e10, -1e10, 2e10, 2e10)

		from ..application import Application
		self._app = Application.instance()

		self._base_transform = QTransform()
		self._zoom_staged = 1.0 # The value to be set
		self._zoom_current = 1.0 # The value currently being displayed
		self._zoom_target = 1.0 # The target to approach for animated navigation
		self._zoom_anchor_uv: Optional[QPointF] = None

		# Pan is normalized between 0 and 1
		self._pan_uv_staged = QPointF(0.5, 0.5) # The value to be set
		self._pan_uv_current = QPointF(0.5, 0.5) # The value currently being displayed
		self._pan_uv_target = QPointF(0.5, 0.5) # The target to approach for animated navigation
		self._pan_uv_anchor: Optional[QPointF] = None
		self._is_panning = False

		# Navigation Animation Timers
		self._navigation_step_timer = QTimer(self)
		self._navigation_step_timer.timeout.connect(self._stepNavigationAnimation)
		self._navigation_step_timer.setTimerType(Qt.TimerType.PreciseTimer)
		self._navigation_step_timer.setInterval(16)  # ~60Hz
		self._navigation_step_tick_clock = QElapsedTimer()

		# Toolbar buttons
		self._activity_button = QToolButton()
		self._activity_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
		self._activity_menu = QMenu()
		for activity in self._app.activities().values():
			action = QAction(activity.IDENTIFIER, self)
			action.triggered.connect(lambda _, a=activity: self.setActivity(a))
			self._activity_menu.addAction(action)
		self._activity_button.setMenu(self._activity_menu)
		self.activityChanged.connect(lambda activity: self._activity_button.setText(f"Activity: {activity.IDENTIFIER}"))

		self._fit_to_window_action = QAction("Fit to Window", self)
		self._fit_to_window_action.triggered.connect(self.fitToWindow)

		# Signals and Slots
		self._app.imageChanged.connect(self._resetBaseTransform)

		# Set the default activity
		self.setActivity(self._app.activities()["Object Detection"])

	def setupToolBar(self, toolbar: QToolBar) -> None:
		super().setupToolBar(toolbar)
		toolbar.addWidget(self._activity_button)
		toolbar.addAction(self._fit_to_window_action)

	# Public Interface -----------------------------------------------------------------------------

	def fitToWindow(self) -> None:
		"""
		Fit the image to the viewport
		"""
		self.setZoom(1.0)
		self.setPan(QPointF(0.5, 0.5))

	def activity(self) -> Activity:
		"""
		Get the current activity
		"""
		return self.scene() # type: ignore


	def setActivity(self, activity: Activity) -> None:
		"""
		Set the current activity
		"""
		self.setScene(activity)
		self.activityChanged.emit(activity)


	def pan(self) -> QPointF:
		"""
		Get the current pan position
		"""
		return self._pan_uv_current


	def setPan(self, pan: QPointF, instant: bool = False) -> None:
		"""
		Set the current pan position
		"""
		self._setPan(pan, instant, _apply=True)


	def zoom(self) -> float:
		"""
		Get the current zoom level
		"""
		return self._zoom_current


	def setZoom(
		self,
		zoom: float,
		anchor_uv: Optional[QPointF] = None,
		instant: bool = False
	) -> None:
		"""
		Set the current zoom level
		"""
		self._setZoom(zoom, anchor_uv, instant, _apply=True)

	# Input Handling -------------------------------------------------------------------------------

	def mousePressEvent(self, event: QMouseEvent) -> None:
		print(
			"Scene position:\n",
			"\tU/V:", self.mapToUv(event.position().toPoint()), "\n",
			"\tScene:", self.mapToScene(event.position().toPoint()), "\n",
			"\tViewport:", event.position().toPoint()
		)
		if event.button() == Qt.MouseButton.MiddleButton or (
			event.button() == Qt.MouseButton.LeftButton and
			event.modifiers() & Qt.KeyboardModifier.AltModifier
		):
			self._pan_uv_anchor = self.mapToUv(event.position().toPoint())
			self._is_panning = True
			event.accept()
			return
		super().mousePressEvent(event)

	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		if self._is_panning:
			assert self._pan_uv_anchor is not None
			delta = self._pan_uv_anchor - self.mapToUv(event.position().toPoint())
			self.setPan(self._pan_uv_current + delta, instant=True)
			event.accept()
			return
		super().mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		self._is_panning = False
		super().mouseReleaseEvent(event)

	def keyPressEvent(self, event: QKeyEvent) -> None:
		if event.key() == Qt.Key.Key_Space:
			self.setPan(QPointF(0.0, 0.0))
			self.setZoom(3.0)
		super().keyPressEvent(event)

	def wheelEvent(self, event: QWheelEvent) -> None:
		step = 1.0010 ** event.angleDelta().y()
		self.setZoom(self._zoom_target * step, anchor_uv=self.mapToUv(event.position().toPoint()), instant=False)

	# Event Handling -------------------------------------------------------------------------------

	def resizeEvent(self, event: QResizeEvent) -> None:
		super().resizeEvent(event)
		self._resetBaseTransform()

	# Navigation -----------------------------------------------------------------------------------

	def _setPan(
		self, pan: QPointF,
		instant: bool = False,
		_apply: bool = True
	):
		self._pan_uv_target = pan
		if instant:
			self._pan_uv_staged = self._pan_uv_target
			if _apply:
				self._applyViewTransform()
			return
		self._scheduleNavigationAnimation()


	def _setZoom(
		self, zoom: float,
		anchor_uv: Optional[QPointF] = None,
		instant: bool = False,
		_apply: bool = True
	) -> None:
		self._zoom_target = max(0.01, float(zoom))
		self._zoom_anchor_uv = anchor_uv
		if instant:
			self._zoom_staged = self._zoom_target
			if _apply:
				self._applyViewTransform()
				self._zoom_anchor_uv = None
			return
		self._scheduleNavigationAnimation()


	def _stepZoomAnimation(self, dt_ms: int) -> bool:
		"""
		Perform a zoom animation step. If no updates occur, return false.
		"""
		if self._zoom_current == self._zoom_target:
			self._zoom_anchor_uv = None
			return False
		alpha = 1.0 - pow(0.5, dt_ms/self.ZOOM_ANIMATION_HALF_LIFE_MS)
		self._zoom_staged = (1.0 - alpha) * self._zoom_current + alpha*self._zoom_target
		if abs(self._zoom_staged - self._zoom_target) < 1e-3:
			# Snap to target if we're close enough
			self._zoom_staged = self._zoom_target
		return True


	def _stepPanAnimation(self, dt_ms: int) -> bool:
		"""
		Perform a pan animation step. If no updates occur, return false.
		"""
		if self._pan_uv_current == self._pan_uv_target:
			return False

		alpha = 1.0 - pow(0.5, dt_ms/self.ZOOM_ANIMATION_HALF_LIFE_MS)
		# Interpolate based on euclidean distance
		delta_x = self._pan_uv_target.x() - self._pan_uv_current.x()
		delta_y = self._pan_uv_target.y() - self._pan_uv_current.y()
		new_x = self._pan_uv_current.x() + alpha * delta_x
		new_y = self._pan_uv_current.y() + alpha * delta_y
		self._pan_uv_staged = QPointF(new_x, new_y)

		if abs(self._pan_uv_staged.x() - self._pan_uv_target.x()) < 1e-3 and \
		   abs(self._pan_uv_staged.y() - self._pan_uv_target.y()) < 1e-3:
			# Snap to target if we're close enough
			self._pan_uv_staged = QPointF(self._pan_uv_target)

		return True


	def _stepNavigationAnimation(self):
		"""
		Perform a navigation animation step. If no updates occur, stop animations.
		"""
		updated = any([
			step(self._navigation_step_tick_clock.elapsed())
			for step in [
				self._stepZoomAnimation,
				self._stepPanAnimation,
			]
		])
		self._navigation_step_tick_clock.restart()
		if updated:
			self._applyViewTransform()
		else:
			self._navigation_step_timer.stop()


	def _scheduleNavigationAnimation(self):
		if self._navigation_step_timer.isActive():
			return
		self._navigation_step_timer.start()
		self._navigation_step_tick_clock.start()

	# Internal -------------------------------------------------------------------------------------

	def _applyViewTransform(self):
		"""
		Applies staged zoom and pan values to make them current.
		Zooms around an anchor point (zoom_anchor_uv, cursor, or center).
		"""
		# Get anchor position before zoom
		if self._zoom_anchor_uv is not None:
			anchor_view_pos_before = self.mapFromUv(self._zoom_anchor_uv)

		zoom_factor = self._zoom_staged / self._zoom_current

		# Rebuild the current transform for numerical stability
		self.setTransform(QTransform(self._base_transform))
		self._zoom_current = self._zoom_staged
		self.scale(self._zoom_current, self._zoom_current)
		viewport_size: QSize = self.viewport().size() # type: ignore
		viewport_size_uv = self.mapToUv(QPoint(viewport_size.width(), viewport_size.height()))
		pan = self._uvToScenePosition(self._pan_uv_current - viewport_size_uv/2.0)
		self.translate(-pan.x(), -pan.y())

		# Adjust pan to keep anchor point fixed
		if self._zoom_anchor_uv is not None and self._pan_uv_staged == self._pan_uv_target:
			delta_uv = self._zoom_anchor_uv - self.mapToUv(anchor_view_pos_before)
			pan = self._uvToScenePosition(delta_uv)
			self.translate(-pan.x(), -pan.y()) # type: ignore
			# Account for the additional pan
			self._pan_uv_current = self._pan_uv_current + delta_uv
			self._pan_uv_staged = self._pan_uv_staged + delta_uv
			self._pan_uv_target = self._pan_uv_target + delta_uv

		# Apply pan
		pan_uv_delta = (self._pan_uv_staged - self._pan_uv_current)*zoom_factor
		pan = self._uvToScenePosition(pan_uv_delta)
		self.translate(-pan.x(), -pan.y())
		self._pan_uv_current = self._pan_uv_staged


	def _resetBaseTransform(self):
		"""
		Reset the base transform based on the current size of the image.
		This ensures that a zoom of 1.0 will exactly fit the image in the viewport
		while maintaining the image's aspect ratio.
		"""
		self._base_transform.reset()
		frame_size = self._frameSize()
		scale_factor = min(self.width()/frame_size.width(), self.height()/frame_size.height())
		self._base_transform.scale(scale_factor, scale_factor)
		self._applyViewTransform()


	def _frameSize(self) -> QSize:
		"""
		Get the size of the frame image in pixels
		"""
		return self.activity()._frame.pixmap().size()

	# Conversions ----------------------------------------------------------------------------------

	def mapToUv(self, pos: QPoint) -> QPointF:
		"""
		Map a viewport position in pixel corodinates to UV coordinates
		"""
		return self._scenePositionToUv(self.mapToScene(pos))

	def mapFromUv(self, pos: QPointF) -> QPoint:
		"""
		Map UV coordinates to viewport's pixel coordinates
		"""
		return self.mapFromScene(self._uvToScenePosition(pos))

	def _scenePositionToUv(self, scene_pos: QPointF):
		frame_size = self._frameSize()
		return QPointF(
			scene_pos.x() / frame_size.width(),
			scene_pos.y() / frame_size.height()
		)

	def _uvToScenePosition(self, normalized_pos: QPointF):
		frame_size = self._frameSize()
		return QPointF(
			normalized_pos.x() * frame_size.width(),
			normalized_pos.y() * frame_size.height()
		)
