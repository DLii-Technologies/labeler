"""A bounded dope sheet for annotation keyframes."""

import math
from uuid import uuid4

from PyQt6.QtCore import QElapsedTimer, QEvent, QPoint, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QContextMenuEvent, QMouseEvent, QNativeGestureEvent, QPainter, QPainterPath, QPen, QWheelEvent
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication, QInputDialog, QMenu, QWidget

from dlii_labeler.activity import Activity, KeyframeableGraphicsItem
from dlii_labeler.operations import operation


class Scrubber(QAbstractScrollArea):
	LAYOUT_KEY = "scrubber_layout"
	RULER_HEIGHT = 30
	ROW_HEIGHT = 28
	LABEL_WIDTH = 160
	DIAMOND_RADIUS = 6
	MAX_PIXELS_PER_FRAME = 512.0

	def __init__(self, parent=None):
		super().__init__(parent)
		from dlii_labeler.application import Application
		self._app = Application.instance()
		self._label_width = self.LABEL_WIDTH
		self._activity: Activity | None = None
		self._rows: list[KeyframeableGraphicsItem] = []
		self._entries: list[tuple[str | None, KeyframeableGraphicsItem | None]] = []
		self._order: list[str] = []
		self._groups: list[dict] = []
		self._selected: set[tuple[KeyframeableGraphicsItem, int]] = set()
		self._zoom_factor = 1.0
		self._pixels_per_frame = 1.0
		self._drag_origin: QPoint | None = None
		self._drag_offset = 0
		self._mode: str | None = None
		self._scrub_x = 0.0
		self._scroll_remainder = 0.0
		self._scrub_clock = QElapsedTimer()
		self._scrub_timer = QTimer(self)
		self._scrub_timer.setInterval(16)
		self._scrub_timer.timeout.connect(self._scrollWhileScrubbing)
		self._pan_origin = QPoint()
		self._pan_scroll = QPoint()
		self._box_start = QPoint()
		self._box_end = QPoint()
		self._box_add = False
		self._selection_anchor: KeyframeableGraphicsItem | None = None
		self._row_press_item: KeyframeableGraphicsItem | None = None
		self._row_pending_single = False
		self._drag_rows: list[KeyframeableGraphicsItem] = []
		self._drop_index = 0
		self._drop_group: str | None = None
		self._drag_group: str | None = None
		self._view_save_timer = QTimer(self)
		self._view_save_timer.setSingleShot(True)
		self._view_save_timer.setInterval(300)
		self._view_save_timer.timeout.connect(self._saveViewState)
		self._restoring_layout = False
		self.setMinimumHeight(110)
		self.setMouseTracking(True)
		self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
		self.horizontalScrollBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)
		self._scrollbar_spacer = QWidget(self)
		self._scrollbar_spacer.setFixedWidth(self._label_width)
		self.addScrollBarWidget(self._scrollbar_spacer, Qt.AlignmentFlag.AlignLeft)
		self._scrollbar_spacer.parentWidget().layout().setSpacing(0)
		self.verticalScrollBar().setFocusPolicy(Qt.FocusPolicy.NoFocus)
		self.setToolTip("Drag the divider to resize object names; drag the ruler to scrub; drag the rows to box select; Ctrl/Command + wheel or pinch to zoom; right click rows for groups and sorting")
		self._app.mediaManager().folderChanged.connect(self._refresh)
		self._app.mediaManager().folderChanged.connect(self._view_save_timer.stop)
		self._app.mediaManager().folderChanged.connect(self._scrub_timer.stop)
		self._app.folderOpened.connect(self._refresh)
		self._app.folderOpened.connect(self._loadLayout)
		self._app.mediaManager().frameIndexChanged.connect(self._onFrameChanged)
		self._app.mediaManager().frameJumped.connect(self._revealFrame)
		self._app.labelSetChanged.connect(self.viewport().update)
		self._app.aboutToQuit.connect(self._flushZoom)
		self._app._operations.restored.connect(self._loadLayout)
		self._refresh()
		self._loadLayout()
		self.horizontalScrollBar().valueChanged.connect(self._scheduleViewSave)
		self.verticalScrollBar().valueChanged.connect(self._scheduleViewSave)

	def setActivity(self, activity: Activity) -> None:
		if self._activity is not None:
			self._activity.changed.disconnect(self._objectsChanged)
			self._activity.selectionChanged.disconnect(self.viewport().update)
			self._activity.timelineSelectionChanged.disconnect(self.viewport().update)
			self._activity.clearTimelineSelection()
		self._activity = activity
		self._selected.clear()
		self._selection_anchor = None
		activity.changed.connect(self._objectsChanged)
		activity.selectionChanged.connect(self.viewport().update)
		activity.timelineSelectionChanged.connect(self.viewport().update)
		self._refresh()

	def _loadLayout(self, *_args) -> None:
		self._view_save_timer.stop()
		store = self._app.dataStore()
		data = store.get(self.LAYOUT_KEY) if store is not None else None
		label_width = data.get("label_width", self.LABEL_WIDTH) if isinstance(data, dict) else self.LABEL_WIDTH
		self._label_width = max(80, label_width) if isinstance(label_width, int) else self.LABEL_WIDTH
		self._order = [value for value in data.get("order", []) if isinstance(value, str)] if isinstance(data, dict) else []
		self._groups = [
			{"id": group["id"], "name": group["name"], "items": [value for value in group.get("items", []) if isinstance(value, str)], "collapsed": bool(group.get("collapsed", False))}
			for group in data.get("groups", [])
			if isinstance(group, dict) and isinstance(group.get("id"), str) and isinstance(group.get("name"), str) and isinstance(group.get("items", []), list)
		] if isinstance(data, dict) else []
		zoom = data.get("zoom", 1.0) if isinstance(data, dict) else 1.0
		self._zoom_factor = float(zoom) if isinstance(zoom, (int, float)) and math.isfinite(zoom) and zoom >= 1 else 1.0
		scroll_frame = data.get("scroll_frame", 0) if isinstance(data, dict) else 0
		scroll_y = data.get("scroll_y", 0) if isinstance(data, dict) else 0
		self._restoring_layout = True
		try:
			self._refresh()
			if isinstance(scroll_frame, (int, float)) and math.isfinite(scroll_frame):
				self.horizontalScrollBar().setValue(round(max(0, scroll_frame) * self._pixels_per_frame))
			if isinstance(scroll_y, int):
				self.verticalScrollBar().setValue(max(0, scroll_y))
		finally:
			self._restoring_layout = False

	def _saveViewState(self) -> None:
		self._saveLayout(mark_modified=False)

	def _saveLayout(self, *, mark_modified: bool = True) -> None:
		self._view_save_timer.stop()
		self._restoring_layout = True
		try:
			self._refresh()
		finally:
			self._restoring_layout = False
		store = self._app.dataStore()
		if store is not None:
			store.set(self.LAYOUT_KEY, {
				"order": self._order, "groups": self._groups, "zoom": self._zoom_factor,
				"scroll_frame": self.horizontalScrollBar().value() / self._pixels_per_frame,
				"scroll_y": self.verticalScrollBar().value(),
				"label_width": self._label_width,
			}, mark_modified=mark_modified)

	def _scheduleViewSave(self, *_args) -> None:
		if not self._restoring_layout and self._app.dataStore() is not None:
			self._view_save_timer.start()

	def _refresh(self, *_args) -> None:
		self._rows = [
			item for item in reversed(self._activity.items())
			if isinstance(item, KeyframeableGraphicsItem)
		] if self._activity is not None else []
		self._order.extend(item.timeline_id for item in self._rows if item.timeline_id not in self._order)
		by_id = {item.timeline_id: item for item in self._rows}
		assigned: set[str] = set()
		self._entries = []
		for group in self._groups:
			self._entries.append((group["id"], None))
			if not group["collapsed"]:
				for value in group["items"]:
					if value in by_id and value not in assigned:
						self._entries.append((group["id"], by_id[value]))
						assigned.add(value)
		for value in self._order:
			if value in by_id and value not in assigned and not any(value in group["items"] for group in self._groups):
				self._entries.append((None, by_id[value]))
		self._selected = {
			(item, frame) for item, frame in self._selected
			if item in self._rows and item.isKeyframed(frame)
		}
		self._updateScrollbars()
		self.viewport().update()

	def _objectsChanged(self) -> None:
		previous = {item.timeline_id for item in self._rows}
		self._refresh()
		if self._restoring_layout:
			return
		for index, (_group, item) in enumerate(self._entries):
			if item is None or item.timeline_id in previous or not item.isSelected():
				continue
			top = index * self.ROW_HEIGHT
			bottom = top + self.ROW_HEIGHT
			bar = self.verticalScrollBar()
			height = self.viewport().height() - self.RULER_HEIGHT
			if top < bar.value():
				bar.setValue(top)
			elif bottom > bar.value() + height:
				bar.setValue(bottom - height)

	def _minimumScale(self) -> float:
		if not self.length():
			return 1.0
		width = max(1, self.viewport().width() - self._label_width - 1)
		step = 1
		while True:
			scale = width / (self.length() - 1 + 2 * step)
			required = self._tickStep(scale)
			if required <= step:
				return scale
			step = required

	def _endPadding(self) -> float:
		return self._tickStep() * self._pixels_per_frame if self.length() else 0.0

	def _updateScrollbars(self) -> None:
		self._label_width = min(self._label_width, max(80, self.viewport().width() - 80))
		self._scrollbar_spacer.setFixedWidth(self._label_width)
		minimum = self._minimumScale()
		self._zoom_factor = min(self._zoom_factor, max(1.0, self.MAX_PIXELS_PER_FRAME / minimum))
		self._pixels_per_frame = minimum * self._zoom_factor
		width = max(1, self.viewport().width() - self._label_width - 1)
		content_width = max(0, self.length() - 1) * self._pixels_per_frame + 2 * self._endPadding()
		self.horizontalScrollBar().setRange(0, max(0, math.floor(content_width - width)))
		self.horizontalScrollBar().setPageStep(width)
		height = max(1, self.viewport().height() - self.RULER_HEIGHT)
		self.verticalScrollBar().setRange(0, max(0, len(self._entries) * self.ROW_HEIGHT - height))
		self.verticalScrollBar().setPageStep(height)

	def resizeEvent(self, event) -> None:
		super().resizeEvent(event)
		self._updateScrollbars()

	def closeEvent(self, event) -> None:
		self._flushZoom()
		super().closeEvent(event)

	def _flushZoom(self) -> None:
		if self._view_save_timer.isActive():
			self._saveViewState()

	def scrollContentsBy(self, _dx: int, _dy: int) -> None:
		self.viewport().update()

	def _x(self, frame: int) -> float:
		return self._label_width + self._endPadding() + frame * self._pixels_per_frame - self.horizontalScrollBar().value()

	def _framePosition(self, x: float) -> float:
		return (x - self._label_width - self._endPadding() + self.horizontalScrollBar().value()) / self._pixels_per_frame

	def _frameAt(self, x: float) -> int:
		frame = round(self._framePosition(x))
		return max(0, min(self.length() - 1, frame))

	def _tickStep(self, scale: float | None = None) -> int:
		width = max(1, self.viewport().width() - self._label_width - 1)
		minimum = min(64, width / 4) / (self._pixels_per_frame if scale is None else scale)
		power = 10 ** math.floor(math.log10(max(1, minimum)))
		for multiplier in (1, 2, 5, 10):
			step = int(power * multiplier)
			if step >= minimum:
				return max(1, step)
		return 1

	def _entryAt(self, y: float) -> tuple[str | None, KeyframeableGraphicsItem | None] | None:
		index = int((y - self.RULER_HEIGHT + self.verticalScrollBar().value()) // self.ROW_HEIGHT)
		return self._entries[index] if y >= self.RULER_HEIGHT and 0 <= index < len(self._entries) else None

	def _rowAt(self, y: float) -> KeyframeableGraphicsItem | None:
		entry = self._entryAt(y)
		return entry[1] if entry is not None else None

	def _keyAt(self, point: QPoint) -> tuple[KeyframeableGraphicsItem, int] | None:
		item = self._rowAt(point.y())
		if item is None or point.x() < self._label_width:
			return None
		frame = self._frameAt(point.x())
		index = next(index for index, (_group, row) in enumerate(self._entries) if row is item)
		y = self.RULER_HEIGHT + index * self.ROW_HEIGHT - self.verticalScrollBar().value() + self.ROW_HEIGHT / 2
		if abs(self._x(frame) - point.x()) <= self.DIAMOND_RADIUS + 3 and abs(y - point.y()) <= self.DIAMOND_RADIUS + 3 and item.isKeyframed(frame):
			return item, frame
		return None

	def _rowName(self, item: KeyframeableGraphicsItem, _index: int) -> str:
		label_set = self._app.labelSet()
		label_id = getattr(item, "label_id", None)
		if not label_id:
			return "Unassigned"
		label = label_set.label(label_id) if label_set is not None and label_id in label_set.active_label_ids() else None
		return label.name if label is not None else "Unknown (Missing Label)"

	def paintEvent(self, _event) -> None:
		p = QPainter(self.viewport())
		width, height = self.viewport().width(), self.viewport().height()
		selected_rows = set(self._activity.selectedAnnotationItems()) if self._activity is not None else set()
		p.fillRect(self.viewport().rect(), QColor("#25272c"))
		p.fillRect(QRectF(0, 0, width, self.RULER_HEIGHT), QColor("#383b42"))
		p.setClipRect(self._label_width, self.RULER_HEIGHT, max(0, width - self._label_width), max(0, height - self.RULER_HEIGHT))
		for index, (_group_id, item) in enumerate(self._entries):
			y = self.RULER_HEIGHT + index * self.ROW_HEIGHT - self.verticalScrollBar().value()
			if y + self.ROW_HEIGHT < self.RULER_HEIGHT or y > height:
				continue
			background = QColor("#30333a" if index % 2 == 0 else "#2b2e34")
			if item in selected_rows:
				background = background.lighter(125)
			p.fillRect(QRectF(self._label_width, y, width - self._label_width, self.ROW_HEIGHT), background)
			p.setPen(QColor("#464951"))
			p.drawLine(self._label_width, int(y + self.ROW_HEIGHT), width, int(y + self.ROW_HEIGHT))
		p.setClipRect(self._label_width, 0, max(0, width - self._label_width), height)
		if self.length():
			step = self._tickStep()
			first = max(0, math.floor(self._framePosition(self._label_width)))
			last = min(self.length() - 1, math.ceil(self._framePosition(width)))
			marks = range(max(0, math.floor(first / step) * step), last + 1, step)
			for frame in marks:
				x = self._x(frame)
				p.setPen(QPen(QColor("#62666e"), 1))
				p.drawLine(int(x), self.RULER_HEIGHT, int(x), height)
				p.setPen(QColor("#d1d4da"))
				text = str(frame)
				p.drawText(QPointF(x - p.fontMetrics().horizontalAdvance(text) / 2, 20), text)
				next_frame = frame + step
				midpoint = (frame + next_frame) / 2
				if step > 1 and midpoint < self.length() - 1:
					middle = self._x(midpoint)
					p.setPen(QPen(QColor("#4b4e55"), 1))
					p.drawLine(int(middle), self.RULER_HEIGHT, int(middle), height)
			p.setPen(QPen(QColor("#f5a623"), 2))
			x = int(self._x(self.currentFrame()))
			p.drawLine(x, 0, x, height)
		p.setClipRect(self._label_width, self.RULER_HEIGHT, max(0, width - self._label_width), max(0, height - self.RULER_HEIGHT))
		for index, (_group_id, item) in enumerate(self._entries):
			if item is None:
				continue
			y = self.RULER_HEIGHT + index * self.ROW_HEIGHT - self.verticalScrollBar().value()
			if y + self.ROW_HEIGHT < self.RULER_HEIGHT or y > height:
				continue
			frames = sorted(
				frame + self._drag_offset if self._mode == "key" and (item, frame) in self._selected else frame
				for frame in item._keyframes
			)
			if len(frames) > 1:
				p.setPen(QPen(QColor("#858b96"), 2))
				center = y + self.ROW_HEIGHT / 2
				p.drawLine(QPointF(self._x(frames[0]), center), QPointF(self._x(frames[-1]), center))
			for frame in item._keyframes:
				key = (item, frame)
				shown_frame = frame + self._drag_offset if self._mode == "key" and key in self._selected else frame
				x = self._x(shown_frame)
				if x < self._label_width - 8 or x > width + 8:
					continue
				center = y + self.ROW_HEIGHT / 2
				r = self.DIAMOND_RADIUS
				path = QPainterPath()
				path.moveTo(x, center - r)
				path.lineTo(x + r, center)
				path.lineTo(x, center + r)
				path.lineTo(x - r, center)
				path.closeSubpath()
				p.setPen(QPen(QColor("#ffffff" if key in self._selected else "#1c1d20"), 1))
				p.setBrush(QColor("#ffbc55" if key in self._selected else "#aeb4be"))
				p.drawPath(path)
		if self._mode == "box":
			box = QRectF(QPointF(self._box_start), QPointF(self._box_end)).normalized().intersected(
				QRectF(self._label_width, self.RULER_HEIGHT, width - self._label_width, height - self.RULER_HEIGHT)
			)
			p.fillRect(box, QColor(103, 160, 245, 45))
			p.setPen(QPen(QColor("#78adf7"), 1))
			p.setBrush(Qt.BrushStyle.NoBrush)
			p.drawRect(box)
		p.setClipping(False)
		p.fillRect(QRectF(0, 0, self._label_width, height), QColor("#34373d"))
		p.setPen(QColor("#545860"))
		p.drawLine(self._label_width - 1, 0, self._label_width - 1, height)
		p.setPen(QColor("#e2e4e8"))
		p.drawText(10, 20, "Objects")
		p.setClipRect(0, self.RULER_HEIGHT, self._label_width, max(0, height - self.RULER_HEIGHT))
		object_ids = {row.timeline_id for row in self._rows}
		for index, (group_id, item) in enumerate(self._entries):
			y = self.RULER_HEIGHT + index * self.ROW_HEIGHT - self.verticalScrollBar().value()
			if y + self.ROW_HEIGHT < self.RULER_HEIGHT or y > height:
				continue
			if item is None:
				group = next(group for group in self._groups if group["id"] == group_id)
				background = "#46658e" if self._mode == "row_drag" and self._drop_group == group_id else "#424751"
				p.fillRect(QRectF(0, y, self._label_width - 1, self.ROW_HEIGHT), QColor(background))
				p.setPen(QColor("#e2e4e8"))
				count = f"({len(object_ids.intersection(group['items']))})"
				count_width = p.fontMetrics().horizontalAdvance(count)
				center = y + self.ROW_HEIGHT / 2
				chevron = QPainterPath()
				if group["collapsed"]:
					chevron.moveTo(12, center - 4)
					chevron.lineTo(16, center)
					chevron.lineTo(12, center + 4)
				else:
					chevron.moveTo(10, center - 2)
					chevron.lineTo(14, center + 2)
					chevron.lineTo(18, center - 2)
				p.save()
				p.setRenderHint(QPainter.RenderHint.Antialiasing)
				p.setBrush(Qt.BrushStyle.NoBrush)
				p.setPen(QPen(QColor("#e2e4e8"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
				p.drawPath(chevron)
				p.restore()
				name_width = max(0, self._label_width - 42 - count_width)
				name = group["name"]
				name = p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, name_width)
				p.drawText(QRectF(26, y, name_width, self.ROW_HEIGHT), Qt.AlignmentFlag.AlignVCenter, name)
				p.setPen(QColor("#b5becb"))
				p.drawText(QRectF(self._label_width - 8 - count_width, y, count_width, self.ROW_HEIGHT), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, count)
				continue
			if item in selected_rows:
				background = QColor("#30333a" if index % 2 == 0 else "#2b2e34").lighter(125)
			else:
				background = QColor("#30333a" if index % 2 == 0 else "#2b2e34")
			p.fillRect(QRectF(0, y, self._label_width - 1, self.ROW_HEIGHT), background)
			p.setPen(QColor("#464951"))
			p.drawLine(0, int(y + self.ROW_HEIGHT), self._label_width - 2, int(y + self.ROW_HEIGHT))
			p.setPen(QColor("#e2e4e8"))
			indent = 24 if group_id is not None else 8
			p.drawText(QRectF(indent, y, self._label_width - indent - 8, self.ROW_HEIGHT), Qt.AlignmentFlag.AlignVCenter, self._rowName(item, index))
		if self._mode == "group_drag" or (self._mode == "row_drag" and self._drop_group is None):
			y = self.RULER_HEIGHT + self._drop_index * self.ROW_HEIGHT - self.verticalScrollBar().value()
			p.setPen(QPen(QColor("#78adf7"), 2))
			p.drawLine(0, int(y), self._label_width - 1, int(y))
		p.setClipping(False)
		p.setPen(QPen(QColor("#62666e"), 1))
		p.drawLine(0, self.RULER_HEIGHT - 1, width, self.RULER_HEIGHT - 1)

	def _canMove(self, offset: int) -> bool:
		if not offset:
			return True
		by_item: dict[KeyframeableGraphicsItem, set[int]] = {}
		for item, frame in self._selected:
			by_item.setdefault(item, set()).add(frame)
		for item, frames in by_item.items():
			destinations = {frame + offset for frame in frames}
			if min(destinations) < 0 or max(destinations) >= self.length():
				return False
			if destinations & (set(item._keyframes) - frames):
				return False
		return True

	@operation("Add object group")
	def _newGroup(self, item: KeyframeableGraphicsItem | None = None) -> None:
		name, accepted = QInputDialog.getText(self, "New Object Group", "Name:")
		if not accepted or not name.strip():
			return
		group = {"id": str(uuid4()), "name": name.strip(), "items": [], "collapsed": False}
		self._groups.append(group)
		if item is not None:
			self._assignGroup(item, group["id"])
		else:
			self._saveLayout()

	@operation("Assign object group")
	def _assignGroup(self, item: KeyframeableGraphicsItem, group_id: str | None) -> None:
		for group in self._groups:
			if item.timeline_id in group["items"]:
				group["items"].remove(item.timeline_id)
		if group_id is not None:
			next(group for group in self._groups if group["id"] == group_id)["items"].append(item.timeline_id)
		self._saveLayout()

	@operation("Reorder objects")
	def _moveRow(self, item: KeyframeableGraphicsItem, direction: int) -> None:
		group = next((group for group in self._groups if item.timeline_id in group["items"]), None)
		visible = group["items"] if group is not None else [value for value in self._order if value in {row.timeline_id for row in self._rows} and not any(value in other["items"] for other in self._groups)]
		index = visible.index(item.timeline_id)
		other = index + direction
		if not 0 <= other < len(visible):
			return
		if group is not None:
			visible[index], visible[other] = visible[other], visible[index]
		else:
			a, b = self._order.index(visible[index]), self._order.index(visible[other])
			self._order[a], self._order[b] = self._order[b], self._order[a]
		self._saveLayout()

	@operation("Sort objects")
	def _sortRows(self, group_id: str | None, by_observation: bool = False) -> None:
		by_id = {item.timeline_id: item for item in self._rows}
		selected = {item.timeline_id for item in self._activity.selectedAnnotationItems()} if self._activity is not None else set()
		eligible = selected if group_id is None and len(selected) >= 2 else set(by_id)
		def sort_key(value: str):
			item = by_id[value]
			return min(item._keyframes, default=float("inf")) if by_observation else self._rowName(item, 0).casefold()
		if group_id is not None:
			orders = [next(group for group in self._groups if group["id"] == group_id)["items"]]
		else:
			orders = [self._order, *(group["items"] for group in self._groups)]
		for order in orders:
			positions = [index for index, value in enumerate(order) if value in eligible and value in by_id]
			values = sorted((order[index] for index in positions), key=sort_key)
			for index, value in zip(positions, values):
				order[index] = value
		self._saveLayout()

	def _selectRow(self, item: KeyframeableGraphicsItem, modifiers: Qt.KeyboardModifier) -> None:
		if self._activity is None:
			return
		current = [row for row in self._activity.selectedAnnotationItems() if row in self._rows]
		ctrl = bool(modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
		shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
		if shift:
			visible = [row for _group, row in self._entries if row is not None]
			anchor = self._selection_anchor if self._selection_anchor in visible else item
			start, end = sorted((visible.index(anchor), visible.index(item)))
			range_items = visible[start:end + 1]
			selected = list(dict.fromkeys(current + range_items)) if ctrl else range_items
		elif ctrl:
			selected = [row for row in current if row is not item] if item in current else current + [item]
			self._selection_anchor = item
		else:
			selected = [item]
			self._selection_anchor = item
		self._activity.setTimelineSelection(selected)

	@operation("Reorder objects")
	def _dropRows(self, rows: list[KeyframeableGraphicsItem], index: int) -> None:
		if not rows:
			return
		target_group, target_item = self._entries[index] if index < len(self._entries) else (None, None)
		if self._drop_group is not None:
			target_group, target_item = self._drop_group, None
		elif target_item is None:
			target_group = None
		if target_item in rows:
			return
		ids = [row.timeline_id for row in rows]
		for group in self._groups:
			group["items"] = [value for value in group["items"] if value not in ids]
		self._order = [value for value in self._order if value not in ids]
		if target_group is not None:
			group = next(group for group in self._groups if group["id"] == target_group)
			position = group["items"].index(target_item.timeline_id) if target_item is not None and target_item.timeline_id in group["items"] else 0
			group["items"][position:position] = ids
		else:
			position = self._order.index(target_item.timeline_id) if target_item is not None and target_item.timeline_id in self._order else len(self._order)
			self._order[position:position] = ids
		self._saveLayout()

	def contextMenuEvent(self, event: QContextMenuEvent) -> None:
		entry = self._entryAt(event.pos().y())
		group_id = entry[0] if entry is not None and entry[1] is None else None
		menu = QMenu(self)
		menu.addAction("Create Group", lambda: self._newGroup())
		if group_id is not None:
			group = next(group for group in self._groups if group["id"] == group_id)
			menu.addAction("Delete Group", lambda: self._deleteGroup(group))
		sort_menu = menu.addMenu("Sort")
		sort_menu.addAction("By Name", lambda: self._sortRows(group_id))
		sort_menu.addAction("By Observation Order", lambda: self._sortRows(group_id, by_observation=True))
		menu.exec(event.globalPos())

	@operation("Rename object group")
	def _renameGroup(self, group: dict) -> None:
		name, accepted = QInputDialog.getText(self, "Rename Object Group", "Name:", text=group["name"])
		if accepted and name.strip():
			group["name"] = name.strip()
			self._saveLayout()

	@operation("Reorder object groups")
	def _moveGroup(self, group: dict, direction: int) -> None:
		index = self._groups.index(group)
		other = index + direction
		if 0 <= other < len(self._groups):
			self._groups[index], self._groups[other] = self._groups[other], self._groups[index]
			self._saveLayout()

	@operation("Delete object group")
	def _deleteGroup(self, group: dict) -> None:
		self._groups.remove(group)
		self._saveLayout()

	def _scrubAt(self, x: float) -> None:
		self._scrub_x = x
		x = max(self._label_width, min(self.viewport().width() - 1, x))
		self.setFrame(self._frameAt(x), reveal=False)

	def _scrollWhileScrubbing(self) -> None:
		if self._mode != "scrub" or not self.isVisible():
			self._scrub_timer.stop()
			return
		elapsed = min(self._scrub_clock.restart() / 1000, 0.05)
		left, right = self._label_width, self.viewport().width() - 1
		margin = min(48, (right - left) / 4)
		if margin <= 0:
			return
		distance = self._scrub_x - (right - margin) if self._scrub_x > right - margin else min(0, self._scrub_x - left - margin)
		speed = math.copysign(300 * min(abs(distance) / margin, 3) ** 2, distance)
		self._scroll_remainder += speed * elapsed
		pixels = math.trunc(self._scroll_remainder)
		self._scroll_remainder -= pixels
		bar = self.horizontalScrollBar()
		bar.setValue(bar.value() + pixels)
		if distance == 0 or bar.value() in (bar.minimum(), bar.maximum()):
			self._scroll_remainder = 0
		self._scrubAt(self._scrub_x)

	def mousePressEvent(self, event: QMouseEvent) -> None:
		point = event.position().toPoint()
		if event.button() == Qt.MouseButton.MiddleButton:
			self._mode = "pan"
			self._pan_origin = point
			self._pan_scroll = QPoint(self.horizontalScrollBar().value(), self.verticalScrollBar().value())
			self.setCursor(Qt.CursorShape.ClosedHandCursor)
			event.accept()
			return
		if event.button() != Qt.MouseButton.LeftButton:
			return
		self.setFocus()
		if self._label_width - 5 <= point.x() < self._label_width:
			self._mode = "resize_labels"
			self.setCursor(Qt.CursorShape.SizeHorCursor)
			event.accept()
			return
		if point.x() >= self._label_width and point.y() < self.RULER_HEIGHT and self.length():
			self._mode = "scrub"
			self._scroll_remainder = 0
			self._scrubAt(point.x())
			self._scrub_clock.start()
			self._scrub_timer.start()
			event.accept()
			return
		key = self._keyAt(point)
		if key is not None:
			if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
				if key in self._selected:
					self._selected.remove(key)
				else:
					self._selected.add(key)
			elif key not in self._selected:
				self._selected = {key}
			self._mode = "key" if key in self._selected else None
			if self._activity is not None:
				self._activity.setTimelineSelection(list({item for item, _frame in self._selected}))
			self._drag_origin = point
			self._drag_offset = 0
		elif point.x() < self._label_width:
			entry = self._entryAt(point.y())
			if entry is not None and entry[1] is None:
				self._drag_group = entry[0]
				self._drag_origin = point
				self._mode = "group"
			elif entry is not None and self._activity is not None:
				item = entry[1]
				modifiers = event.modifiers()
				current = [row for row in self._activity.selectedAnnotationItems() if row in self._rows]
				self._row_pending_single = not modifiers and item in current and len(current) > 1
				if not self._row_pending_single:
					self._selectRow(item, modifiers)
				self._row_press_item = item
				self._drag_origin = point
				self._mode = "row" if not modifiers else None
			else:
				self._mode = None
		else:
			self._mode = "box"
			self._box_start = point
			self._box_end = point
			self._box_add = bool(event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier))
		self.viewport().update()
		event.accept()

	def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
		entry = self._entryAt(event.position().y())
		if event.button() == Qt.MouseButton.LeftButton and entry is not None and entry[1] is not None:
			item = entry[1]
			self._selectRow(item, Qt.KeyboardModifier.NoModifier)
			if item._keyframes:
				key = self._keyAt(event.position().toPoint())
				frame = key[1] if key is not None else min(item._keyframes, key=lambda value: (abs(value - self.currentFrame()), value))
				self.setFrame(frame)
			event.accept()
			return
		super().mouseDoubleClickEvent(event)

	def mouseMoveEvent(self, event: QMouseEvent) -> None:
		point = event.position().toPoint()
		if self._mode == "resize_labels":
			self._label_width = max(80, min(point.x(), self.viewport().width() - 80))
			self._updateScrollbars()
			self.viewport().update()
			self._scheduleViewSave()
		elif self._mode is None:
			self.setCursor(Qt.CursorShape.SizeHorCursor if self._label_width - 5 <= point.x() < self._label_width else Qt.CursorShape.ArrowCursor)
		elif self._mode == "pan":
			self.horizontalScrollBar().setValue(self._pan_scroll.x() + self._pan_origin.x() - point.x())
			self.verticalScrollBar().setValue(self._pan_scroll.y() + self._pan_origin.y() - point.y())
		elif self._mode == "scrub" and self.length():
			self._scrubAt(point.x())
		elif self._mode == "key" and self._drag_origin is not None:
			offset = round((point.x() - self._drag_origin.x()) / self._pixels_per_frame)
			self._drag_offset = offset if self._canMove(offset) else 0
			self.viewport().update()
		elif self._mode == "box":
			self._box_end = point
			self.viewport().update()
		elif self._mode in ("group", "group_drag") and self._drag_origin is not None:
			if (point - self._drag_origin).manhattanLength() >= QApplication.startDragDistance():
				self._mode = "group_drag"
			if self._mode == "group_drag":
				position = (point.y() - self.RULER_HEIGHT + self.verticalScrollBar().value()) / self.ROW_HEIGHT
				# Snap to boundaries between whole groups, never among their children.
				boundaries = [index for index, (_group, item) in enumerate(self._entries) if item is None]
				boundaries.append(next((index for index, (group, _item) in enumerate(self._entries) if group is None), len(self._entries)))
				self._drop_index = min(boundaries, key=lambda index: abs(index - position))
				self.viewport().update()
		elif self._mode in ("row", "row_drag") and self._drag_origin is not None:
			if self._mode == "row" and (point - self._drag_origin).manhattanLength() >= QApplication.startDragDistance():
				self._mode = "row_drag"
				selected = set(self._activity.selectedAnnotationItems()) if self._activity is not None else set()
				self._drag_rows = [row for _group, row in self._entries if row is not None and row in selected]
			if self._mode == "row_drag":
				position = (point.y() - self.RULER_HEIGHT + self.verticalScrollBar().value()) / self.ROW_HEIGHT
				self._drop_index = max(0, min(len(self._entries), round(position)))
				entry = self._entryAt(point.y()) if 0 <= point.x() < self._label_width else None
				self._drop_group = entry[0] if entry is not None and entry[1] is None else None
				self.viewport().update()
		event.accept()

	@operation("Edit timeline")
	def mouseReleaseEvent(self, event: QMouseEvent) -> None:
		self._scrub_timer.stop()
		if self._mode == "resize_labels":
			self._scheduleViewSave()
			self.unsetCursor()
		if event.button() == Qt.MouseButton.MiddleButton:
			self.unsetCursor()
		if event.button() == Qt.MouseButton.LeftButton and self._mode == "key" and self._drag_offset:
			by_item: dict[KeyframeableGraphicsItem, set[int]] = {}
			for item, frame in self._selected:
				by_item.setdefault(item, set()).add(frame)
			for item, frames in by_item.items():
				item.moveKeyframes(frames, self._drag_offset)
			self._selected = {(item, frame + self._drag_offset) for item, frame in self._selected}
			if self._activity is not None:
				self._activity.changed.emit()
		if event.button() == Qt.MouseButton.LeftButton and self._mode == "box":
			box = QRectF(QPointF(self._box_start), QPointF(self._box_end)).normalized()
			if not self._box_add:
				self._selected.clear()
			for index, (_group_id, item) in enumerate(self._entries):
				if item is None:
					continue
				y = self.RULER_HEIGHT + index * self.ROW_HEIGHT - self.verticalScrollBar().value() + self.ROW_HEIGHT / 2
				if box.top() <= y <= box.bottom():
					for frame in item._keyframes:
						if box.left() <= self._x(frame) <= box.right():
							self._selected.add((item, frame))
			if self._activity is not None:
				self._activity.setTimelineSelection(list({item for item, _frame in self._selected}))
		if event.button() == Qt.MouseButton.LeftButton and self._mode == "row" and self._row_pending_single and self._row_press_item is not None:
			self._selectRow(self._row_press_item, Qt.KeyboardModifier.NoModifier)
		if event.button() == Qt.MouseButton.LeftButton and self._mode == "row_drag":
			self._dropRows(self._drag_rows, self._drop_index)
		if event.button() == Qt.MouseButton.LeftButton and self._mode in ("group", "group_drag"):
			group = next(group for group in self._groups if group["id"] == self._drag_group)
			if self._mode == "group":
				group["collapsed"] = not group["collapsed"]
			else:
				target = self._entries[self._drop_index][0] if self._drop_index < len(self._entries) else None
				if target != self._drag_group:
					self._groups.remove(group)
					index = next((index for index, other in enumerate(self._groups) if other["id"] == target), len(self._groups))
					self._groups.insert(index, group)
			self._saveLayout()
		self._mode = None
		self._row_press_item = None
		self._row_pending_single = False
		self._drag_rows = []
		self._drop_group = None
		self._drag_group = None
		self._drag_offset = 0
		self.viewport().update()
		event.accept()

	def wheelEvent(self, event: QWheelEvent) -> None:
		angle = event.angleDelta()
		if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
			if not self.length() or not angle.y():
				return
			anchor = self.viewport().mapFromGlobal(event.globalPosition().toPoint()).x()
			self._zoomAt(anchor, 1.2 ** (angle.y() / 120))
		elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
			self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - angle.y())
		else:
			if angle.x():
				self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - angle.x())
			else:
				self.verticalScrollBar().setValue(self.verticalScrollBar().value() - angle.y())
		self.viewport().update()
		event.accept()

	def _zoomAt(self, anchor: float, factor: float) -> None:
		if not self.length():
			return
		anchor = max(self._label_width, min(self.viewport().width() - 1, anchor))
		frame = self._framePosition(anchor)
		self._zoom_factor = max(1.0, min(max(1.0, self.MAX_PIXELS_PER_FRAME / self._minimumScale()), self._zoom_factor * factor))
		self._updateScrollbars()
		self.horizontalScrollBar().setValue(round(self._endPadding() + frame * self._pixels_per_frame - (anchor - self._label_width)))
		self.viewport().update()
		self._scheduleViewSave()

	def viewportEvent(self, event) -> bool:
		if event.type() == QEvent.Type.NativeGesture:
			gesture: QNativeGestureEvent = event
			if gesture.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
				anchor = self.viewport().mapFromGlobal(gesture.globalPosition().toPoint()).x()
				self._zoomAt(anchor, 2.0 ** gesture.value())
				event.accept()
				return True
		return super().viewportEvent(event)

	def keyPressEvent(self, event) -> None:
		if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Right, Qt.Key.Key_Down):
			delta = -1 if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up) else 1
			self.setFrame(self.currentFrame() + delta, reveal=False)
			event.accept()
			return
		if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self._selected:
			self._deleteSelectedKeys()
			event.accept()
			return
		super().keyPressEvent(event)

	@operation("Delete keyframes")
	def _deleteSelectedKeys(self) -> None:
		for item, frame in self._selected:
			item.removeKeyframe(frame)
		self._selected.clear()
		if self._activity is not None:
			self._activity.changed.emit()

	def _onFrameChanged(self, _index: int) -> None:
		self.viewport().update()

	def _revealFrame(self, _index: int) -> None:
		x = self._x(self.currentFrame())
		left, right = self._label_width, self.viewport().width() - 1
		if x < left or x > right:
			center = (left + right) / 2
			self.horizontalScrollBar().setValue(round(self.horizontalScrollBar().value() + x - center))
			self._saveViewState()
		self.viewport().update()

	def currentFrame(self) -> int:
		return self._app.mediaManager().index()

	def setFrame(self, index: int, *, reveal: bool = True) -> None:
		if self.length():
			self._app.mediaManager().setIndex(max(0, min(self.length() - 1, index)), reveal=reveal)

	def length(self) -> int:
		return self._app.mediaManager().length()
