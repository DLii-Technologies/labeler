from typing import Optional
from PyQt6.QtCore import (
	pyqtSignal,
	QElapsedTimer,
	QEvent,
	QPoint,
	QPointF,
	QRectF,
	QSize,
	Qt,
	QTimer
)
from PyQt6.QtGui import (
	QCursor,
	QInputDevice,
	QKeyEvent,
	QMouseEvent,
	QNativeGestureEvent,
	QPalette,
	QPainterPath,
	QPen,
	QResizeEvent,
	QTransform,
	QWheelEvent
)
from PyQt6.QtWidgets import (
	QComboBox,
	QGraphicsView,
	QPushButton,
	QProxyStyle,
	QStyle,
	QStyleFactory,
	QStyleOptionComboBox,
	QStylePainter,
	QToolBar,
	QVBoxLayout,
	QWidget
)

from ..activity import Activity
from .pane_widget import PaneWidget


class DropdownStyle(QProxyStyle):
	def styleHint(self, hint, option=None, widget=None, returnData=None):
		if hint == QStyle.StyleHint.SH_ComboBox_Popup:
			return 0
		return super().styleHint(hint, option, widget, returnData)


class LabeledComboBox(QComboBox):
	"""A compact labeled dropdown using the app palette and standard combo-box behavior."""
	def __init__(self, label: str):
		super().__init__()
		self._field_label = label
		self.setAccessibleName(label)
		self.setFixedHeight(32)
		self.setMinimumWidth(200)
		self.setMaximumWidth(260)
		style = DropdownStyle(QStyleFactory.create(self.style().objectName()))
		style.setParent(self)
		self.setStyle(style)
		self.currentTextChanged.connect(self._updateToolTip)

	def _updateToolTip(self, text: str) -> None:
		self.setToolTip(f"{self._field_label}: {text}")

	def sizeHint(self) -> QSize:
		return QSize(230, 32)

	def showPopup(self) -> None:
		super().showPopup()
		popup = self.view().window()
		if not popup.isVisible():
			return
		bounds = self.screen().availableGeometry()
		below = self.mapToGlobal(QPoint(0, self.height()))
		popup.resize(min(max(self.width(), popup.width()), bounds.width()), min(popup.height(), bounds.height()))
		x = max(bounds.left(), min(below.x(), bounds.right() - popup.width() + 1))
		y = below.y()
		if y + popup.height() > bounds.bottom() + 1:
			y = self.mapToGlobal(QPoint(0, 0)).y() - popup.height()
		y = max(bounds.top(), min(y, bounds.bottom() - popup.height() + 1))
		popup.move(x, y)

	def paintEvent(self, event) -> None:
		option = QStyleOptionComboBox()
		self.initStyleOption(option)
		text_group = QPalette.ColorGroup.Active if self.isEnabled() else QPalette.ColorGroup.Disabled
		text_color = option.palette.color(text_group, QPalette.ColorRole.ButtonText)
		painter = QStylePainter(self)
		painter.setRenderHint(QStylePainter.RenderHint.Antialiasing)
		background = option.palette.color(QPalette.ColorRole.Button)
		if option.state & QStyle.StateFlag.State_MouseOver:
			background = background.lighter(108)
		border_role = QPalette.ColorRole.Highlight if self.hasFocus() else QPalette.ColorRole.Mid
		painter.setPen(QPen(option.palette.color(border_role), 1))
		painter.setBrush(background)
		painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 5, 5)
		painter.setPen(QPen(text_color, 1.5))
		painter.setBrush(Qt.BrushStyle.NoBrush)
		arrow = QPainterPath()
		arrow.moveTo(self.width() - 24, self.height() / 2 - 2)
		arrow.lineTo(self.width() - 19, self.height() / 2 + 3)
		arrow.lineTo(self.width() - 14, self.height() / 2 - 2)
		painter.drawPath(arrow)
		rect = self.rect().adjusted(12, 2, -34, -2)
		painter.setClipRect(rect)
		painter.setFont(self.font())
		painter.setPen(text_color)
		painter.setOpacity(0.65)
		caption = rect.adjusted(0, 0, 0, 0)
		label = self._field_label + ":"
		caption.setWidth(painter.fontMetrics().horizontalAdvance(label))
		painter.drawText(caption, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
		painter.setOpacity(1)
		value = rect.adjusted(0, 0, 0, 0)
		value.setLeft(caption.right() + 7)
		text = painter.fontMetrics().elidedText(self.currentText(), Qt.TextElideMode.ElideRight, value.width())
		painter.drawText(value, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)


class ViewportWidget(PaneWidget, QGraphicsView):

	ZOOM_ANIMATION_HALF_LIFE_MS = 45
	PAN_ANIMATION_HALF_LIFE_MS = 1000
	ACTIVITY_DATA_KEY = "viewport_activity"
	NAVIGATION_DATA_KEY = "viewport_navigation"

	activityChanged = pyqtSignal(Activity)

	SCANCODES = {
		'A': {'windows': 30, 'linux': 38, 'macos': 0},
		'D': {'windows': 32, 'linux': 39, 'macos': 0}
	}

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
		self.setSceneRect(-float("inf"), -float("inf"), float("inf"), float("inf"))

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

		self._gesture_zoom_active = False
		self._gesture_last_pos: QPointF | None = None

		# Navigation Animation Timers
		self._navigation_step_timer = QTimer(self)
		self._navigation_step_timer.timeout.connect(self._stepNavigationAnimation)
		self._navigation_step_timer.setTimerType(Qt.TimerType.PreciseTimer)
		self._navigation_step_timer.setInterval(16)  # ~60Hz
		self._navigation_step_tick_clock = QElapsedTimer()

		# Toolbar buttons
		self._activity_combo = LabeledComboBox("Activity")
		for activity in self._app.activities().values():
			self._activity_combo.addItem(activity.IDENTIFIER, activity.IDENTIFIER)
		self._activity_combo.activated.connect(self._selectActivity)

		self._label_set_combo = LabeledComboBox("Label set")
		self._label_set_combo.activated.connect(self._selectLabelSet)
		self._app.labelSetChanged.connect(self._refreshLabelSets)
		self._app.labelCatalogChanged.connect(self._refreshLabelSets)

		self._recenter_button = QPushButton("Recenter")
		self._recenter_button.setFont(self._activity_combo.font())
		self._recenter_button.setFixedHeight(32)
		self._recenter_button.setStyleSheet(
			"QPushButton { padding: 0px 14px; border: 1px solid palette(mid); "
			"border-radius: 5px; background: palette(button); color: palette(button-text); }"
			"QPushButton:hover { border-color: palette(highlight); }"
			"QPushButton:pressed { background: palette(mid); }"
			"QPushButton:focus { border-color: palette(highlight); }"
		)
		self._recenter_button.clicked.connect(self.recenter)

		# Signals and Slots
		self._app.mediaManager().frameChanged.connect(self._resetBaseTransform)

		self._app.folderOpened.connect(self._restoreActivity)
		self._app.folderOpened.connect(self._restoreNavigationState)
		self._restoreActivity()
		self._restoreNavigationState()

	def setupToolBar(self, toolbar: QToolBar) -> None:
		super().setupToolBar(toolbar)
		toolbar.setStyleSheet("QToolBar { margin: 0px; padding: 0px; spacing: 2px; }")
		for index, combo in enumerate((self._activity_combo, self._label_set_combo)):
			combo.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)
			container = QWidget()
			container.setFixedHeight(combo.height() + 12)
			layout = QVBoxLayout(container)
			layout.setContentsMargins(6 if index == 0 else 0, 6, 0, 6)
			layout.setSpacing(0)
			layout.addWidget(combo)
			toolbar.addWidget(container)
		toolbar.addWidget(self._recenter_button)
		self._refreshLabelSets()

	def _refreshLabelSets(self, *_args) -> None:
		current = self._app.labelSet()
		current_id = current.id if current is not None else None
		catalog_sets = sorted(self._app.labelCatalog().all(), key=lambda value: value.name.lower())
		self._label_set_combo.blockSignals(True)
		try:
			self._label_set_combo.clear()
			self._label_set_combo.addItem("No label set", None)
			catalog_ids = set()
			for label_set in catalog_sets:
				catalog_ids.add(label_set.id)
				self._label_set_combo.addItem(label_set.name, label_set.id)
			if current is not None and current.id not in catalog_ids:
				self._label_set_combo.addItem(f"{current.name} (local copy)", current.id)
			index = self._label_set_combo.findData(current_id)
			self._label_set_combo.setCurrentIndex(index if index >= 0 else 0)
		finally:
			self._label_set_combo.blockSignals(False)

	def _selectLabelSet(self, index: int) -> None:
		set_id = self._label_set_combo.itemData(index)
		if set_id is None:
			self._app.clearLabelSet()
		else:
			self._app.setLabelSet(set_id)

	def _selectActivity(self, index: int) -> None:
		self.setActivity(self._app.activities()[self._activity_combo.itemData(index)])

	# Public Interface -----------------------------------------------------------------------------

	def recenter(self) -> None:
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
		self._activity_combo.setCurrentIndex(self._activity_combo.findData(activity.IDENTIFIER))
		data_store = self._app.dataStore()
		if data_store is not None:
			data_store.set(self.ACTIVITY_DATA_KEY, activity.IDENTIFIER, mark_modified=False)
		self.activityChanged.emit(activity)


	def _restoreActivity(self, *_args) -> None:
		default_activity = self._app.activities()["Object Detection"]
		activity_identifier = None
		data_store = self._app.dataStore()
		if data_store is not None:
			activity_identifier = data_store.get(self.ACTIVITY_DATA_KEY)
		if not isinstance(activity_identifier, str):
			activity_identifier = default_activity.IDENTIFIER
		activity = self._app.activities().get(activity_identifier, default_activity)
		self.setActivity(activity)


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
		self._saveNavigationState()

	def isZooming(self) -> bool:
		"""
		Check if we are currently zooming
		"""
		return self._zoom_current != self._zoom_target


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
		self._saveNavigationState()


	def _saveNavigationState(self) -> None:
		data_store = self._app.dataStore()
		if data_store is None:
			return
		data_store.set(self.NAVIGATION_DATA_KEY, {
			"zoom": self._zoom_target,
			"pan": (self._pan_uv_target.x(), self._pan_uv_target.y()),
		}, mark_modified=False)


	def _restoreNavigationState(self, *_args) -> None:
		zoom = 1.0
		pan = QPointF(0.5, 0.5)
		data_store = self._app.dataStore()
		navigation_data = data_store.get(self.NAVIGATION_DATA_KEY) if data_store is not None else None
		if isinstance(navigation_data, dict):
			stored_zoom = navigation_data.get("zoom")
			stored_pan = navigation_data.get("pan")
			if isinstance(stored_zoom, (int, float)):
				zoom = max(0.01, float(stored_zoom))
			if (
				isinstance(stored_pan, (tuple, list))
				and len(stored_pan) == 2
				and all(isinstance(value, (int, float)) for value in stored_pan)
			):
				pan = QPointF(float(stored_pan[0]), float(stored_pan[1]))

		self._navigation_step_timer.stop()
		self._setZoom(zoom, instant=True, _apply=False)
		self._setPan(pan, instant=True, _apply=False)
		self._applyViewTransform()
		self._saveNavigationState()

	# Input Handling -------------------------------------------------------------------------------

	def mousePressEvent(self, event: QMouseEvent) -> None:
		if event.button() == Qt.MouseButton.MiddleButton:
			self._pan_uv_anchor = self.mapToUv(event.position().toPoint())
			self._is_panning = True
			event.accept()
			return
		super().mousePressEvent(event)


	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		event.accept()
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
		media_manager = self._app.mediaManager()
		frame_index = media_manager.currentFrameIndex()
		frame_count = media_manager.length()
		if (event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_A) and frame_index > 0:
			media_manager.setIndex(frame_index - 1, reveal=False)
			event.accept()
			return
		# Harcode Dvorak alternative to D for right for now
		if (event.key() == Qt.Key.Key_Right or event.key() in (Qt.Key.Key_D, Qt.Key.Key_E)) and frame_index < frame_count - 1:
			media_manager.setIndex(frame_index + 1, reveal=False)
			event.accept()
			return
		# Filter
		if event.key() not in (
			Qt.Key.Key_Left,
			Qt.Key.Key_Right,
			Qt.Key.Key_Up,
			Qt.Key.Key_Down
		):
			super().keyPressEvent(event)


	def _uvDeltaFromViewportDelta(self, delta_px: QPointF) -> QPointF:
		# Convert a viewport-pixel translation into a UV translation.
		p0 = QPointF(self.rect().center())
		p1 = p0 + delta_px
		return self.mapToUv(p1.toPoint()) - self.mapToUv(p0.toPoint())


	def wheelEvent(self, event: QWheelEvent) -> None:
		# During an active pinch stream, ignore wheel-based scrolling so the
		# pinch handler owns the interaction.
		if self._gesture_zoom_active:
			event.accept()
			return

		pixel_delta = event.pixelDelta()

		# Trackpad two-finger scroll -> pan
		if (
			not pixel_delta.isNull()
			and event.device() is not None
			and event.device().type() == QInputDevice.DeviceType.TouchPad
		):
			uv_delta = self._uvDeltaFromViewportDelta(QPointF(pixel_delta))
			self.setPan(self.pan() - uv_delta, instant=True)
			event.accept()
			return

		# Mouse wheel -> zoom
		angle_y = event.angleDelta().y()
		if angle_y != 0:
			step = 1.0010 ** angle_y
			self.setZoom(
				self._zoom_target * step,
				anchor_uv=self.mapToUv(event.position().toPoint()),
				instant=False,
			)
			event.accept()
			return

		event.ignore()
		super().wheelEvent(event)
	# Event Handling -------------------------------------------------------------------------------

	def event(self, event):
		if event.type() == QEvent.Type.NativeGesture:
			gesture: QNativeGestureEvent = event

			if gesture.gestureType() == Qt.NativeGestureType.BeginNativeGesture:
				self._gesture_zoom_active = False
				self._gesture_last_pos = gesture.position()
				event.accept()
				return True

			if gesture.gestureType() == Qt.NativeGestureType.EndNativeGesture:
				self._gesture_zoom_active = False
				self._gesture_last_pos = None
				event.accept()
				return True

			if gesture.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
				pos = gesture.position()

				# During a pinch, treat movement of the gesture anchor as pan.
				if self._gesture_last_pos is not None:
					delta_px = pos - self._gesture_last_pos
					if not delta_px.isNull():
						uv_delta = self._uvDeltaFromViewportDelta(delta_px)
						self.setPan(self.pan() - uv_delta, instant=True)

				self._gesture_last_pos = pos
				self._gesture_zoom_active = True

				# event.value() is the zoom delta for ZoomNativeGesture.
				step = 2.0 ** gesture.value()
				self.setZoom(
					self._zoom_target * step,
					anchor_uv=self.mapToUv(pos.toPoint()),
					instant=False,
				)
				event.accept()
				return True

		return super().event(event)

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
