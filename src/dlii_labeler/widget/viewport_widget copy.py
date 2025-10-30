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

	ANIMATION_HALF_LIFE_MS = 45

	activityChanged = pyqtSignal(Activity)

	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)

		# self.setAlignment(Qt.AlignmentFlag.AlignAbsolute)
		self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

		self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
		self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

		# Disable scrollbars
		# self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
		# self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

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

		self.setActivity(self._app.activities()["Object Detection"])

		# Signals and Slots
		self._app.imageChanged.connect(self._resetBaseTransform)


	# Public Interface -----------------------------------------------------------------------------

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
			self.setPan(self._pan_uv_current + QPointF(0.1, 0.1), instant=True)
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
		self._pan_uv_target = self._clampPan(pan)
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
		alpha = 1.0 - pow(0.5, dt_ms/self.ANIMATION_HALF_LIFE_MS)
		self._zoom_staged = (1.0 - alpha) * self._zoom_current + alpha * self._zoom_target
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

		alpha = 1.0 - pow(0.5, dt_ms/self.ANIMATION_HALF_LIFE_MS)
		new_x = (1.0 - alpha) * self._pan_uv_current.x() + alpha * self._pan_uv_target.x()
		new_y = (1.0 - alpha) * self._pan_uv_current.y() + alpha * self._pan_uv_target.y()
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
		# Apply zoom
		transform = QTransform(self._base_transform)
		self._zoom_current = self._zoom_staged
		transform.scale(self._zoom_current, self._zoom_current)
		self.setTransform(transform)
		self._updateSceneRect()

		# Apply pan
		self._pan_uv_current = self._clampPan(self._pan_uv_staged)
		print(f"Panning to {self._pan_uv_current}", self._frameSize(), self.mapFromUv(self._pan_uv_current))
		pan = self.uvUnitToSceneUnit(self._pan_uv_current)
		self.translate(-pan.x(), -pan.y())

		# self.centerOn(self._uvToScenePosition(self._pan_uv_current))

		# anchor = self._zoom_anchor_uv
		# if anchor is not None:
		# 	anchor_scene_pos = self._uvToScenePosition(anchor)

		# # Rebuild the current transform from known values
		# transform = QTransform(self._base_transform)
		# transform.scale(self._zoom_current, self._zoom_current)
		# pan = self.uvUnitToSceneUnit(self._pan_uv_current)
		# transform.translate(-pan.x(), -pan.y())

		# print("Rebuilt Transform")
		# for i in range(3):
		# 	for j in range(3):
		# 		print(f"{getattr(transform, f'm{i+1}{j+1}')():.2f}", end=" ")
		# 	print()
		# transform = self.transform()
		# print("Current")
		# for i in range(3):
		# 	for j in range(3):
		# 		print(f"{getattr(transform, f'm{i+1}{j+1}')():.2f}", end=" ")
		# 	print()

		# # Zoom
		# if anchor is not None:
		# 	transform.translate(+anchor_scene_pos.x(), +anchor_scene_pos.y())
		# factor = self._zoom_staged / self._zoom_current
		# transform.scale(factor, factor)
		# if anchor is not None:
		# 	transform.translate(-anchor_scene_pos.x(), -anchor_scene_pos.y())
		# self._zoom_current = self._zoom_staged
		# self.setTransform(transform)
		# self._updateSceneRect()

		# Apply pan
		# self._pan_uv_staged = self._clampPan(self._pan_uv_staged)
		# delta = self._uvToScenePosition(self._pan_uv_staged) - self._uvToScenePosition(self._pan_uv_current)
		# self.translate(-delta.x(), -delta.y())
		# self._pan_uv_current = self._pan_uv_staged



	def _clampPan(self, pan_uv: QPointF) -> QPointF:
		"""
		Clamp a normalized pan (viewport center in U/V) to the valid range for the
		current zoom and viewport size. No side effects; returns the clamped U/V.
		"""
		# Viewport size in pixels
		vp_w = self.viewport().width()
		vp_h = self.viewport().height()

		# Map viewport basis to normalized scene to get visible span in U/V
		p00 = self.mapToUv(QPoint(0, 0))
		p10 = self.mapToUv(QPoint(vp_w, 0))
		p01 = self.mapToUv(QPoint(0, vp_h))

		vis_u = abs(p10.x() - p00.x())  # viewport width in normalized coords
		vis_v = abs(p01.y() - p00.y())  # viewport height in normalized coords

		# Scene rect (in normalized coords) was expanded to [-vis_u, 1+vis_u] × [-vis_v, 1+vis_v].
		# To keep the *viewport* fully inside that rect, the center must lie within:
		#   U in [ -vis_u + vis_u/2, 1 + vis_u - vis_u/2 ] == [ -vis_u/2, 1 + vis_u/2 ]
		#   V in [ -vis_v/2, 1 + vis_v/2 ]
		u_min = -vis_u * 0.5
		u_max = 1.0 + vis_u * 0.5
		v_min = -vis_v * 0.5
		v_max = 1.0 + vis_v * 0.5

		print(u_min, u_max, v_min, v_max)

		u = max(u_min, min(pan_uv.x(), u_max))
		v = max(v_min, min(pan_uv.y(), v_max))
		return QPointF(u, v)


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


	def _updateSceneRect(self):
		"""
		Ensures the scene rect is large enough so that we can pan the frame
		just outside the viewport, regardless of the current zoom.

		Call whenever image size, window size, or zoom changes.
		"""
		activity = self.scene()
		if activity is None:
			return

		# --- how much of the frame fits in the viewport *in normalized coords*?
		# normalized (U,V) width/height of the *visible* viewport
		vp_w = self.viewport().width()
		vp_h = self.viewport().height()

		# map three viewport points to normalized-scene space
		p00 = self.mapToUv(QPoint(0, 0))
		p10 = self.mapToUv(QPoint(vp_w, 0))
		p01 = self.mapToUv(QPoint(0, vp_h))

		# visible size in normalized units (U,V). This automatically accounts
		# for base transform + user zoom.
		vis_u = abs(p10.x() - p00.x())
		vis_v = abs(p01.y() - p00.y())

		# we want to be able to pan so the frame can sit just outside the viewport.
		# that's exactly the old logic: add a margin equal to the viewport size
		# (expressed in scene units). In normalized space the frame is [0,1]x[0,1],
		# so expand to [-vis_u, 1+vis_u] x [-vis_v, 1+vis_v].
		ul_norm = QPointF(-vis_u, -vis_v)        # upper-left in normalized coords
		br_norm = QPointF(1.0 + vis_u, 1.0 + vis_v)  # bottom-right in normalized coords

		# convert back to *scene* coordinates (pixel-ish, centered on the frame)
		ul_scene = self._uvToScenePosition(ul_norm)
		br_scene = self._uvToScenePosition(br_norm)

		# set the scene rect in scene coordinates
		self.setSceneRect(
			ul_scene.x(),
			ul_scene.y(),
			br_scene.x() - ul_scene.x(),
			br_scene.y() - ul_scene.y(),
		)

		self._pan_uv_current = self._clampPan(self._pan_uv_current)


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
