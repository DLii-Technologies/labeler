from dataclasses import dataclass
import math
import numpy as np
from typing import Any, Dict, Optional
from PyQt6.QtCore import (
	QRectF,
	QPointF,
	Qt
)
from PyQt6.QtGui import (
	QColor,
	QPainter,
	QPen
)
from PyQt6.QtWidgets import (
	QGraphicsItem,
	QGraphicsRectItem,
	QGraphicsSceneHoverEvent,
	QGraphicsSceneMouseEvent,
	QGraphicsView,
	QStyle,
	QStyleOptionGraphicsItem
)

from . import KeyframeableGraphicsItem, SaveableGraphicsItem
from .perspective_plane_activity import PerspectivePlaneActivity

class BoxItem(QGraphicsRectItem, KeyframeableGraphicsItem, SaveableGraphicsItem):

	MIN_HANDLE_MARGIN = 6
	HANDLE_SIZE = 6
	MIN_SIZE = 1.0
	SHADOW_WIDTH = 16

	@dataclass
	class State:
		u: float
		v: float
		width: float
		height: float

	class Sides:
		NONE = 0
		E = 1
		W = 2
		N = 4
		S = 8

	CURSORS = {
		Sides.NONE: Qt.CursorShape.ArrowCursor,
		Sides.E: Qt.CursorShape.SizeHorCursor,
		Sides.W: Qt.CursorShape.SizeHorCursor,
		Sides.N: Qt.CursorShape.SizeVerCursor,
		Sides.S: Qt.CursorShape.SizeVerCursor,
		Sides.N | Sides.W: Qt.CursorShape.SizeFDiagCursor,
		Sides.S | Sides.E: Qt.CursorShape.SizeFDiagCursor,
		Sides.N | Sides.E: Qt.CursorShape.SizeBDiagCursor,
		Sides.S | Sides.W: Qt.CursorShape.SizeBDiagCursor
	}

	def __init__(
		self,
		rect: QRectF = QRectF(),
		label_id: Optional[str] = None,
		metadata: Optional[Dict[str, Any]] = None,
		plane_id: Optional[str] = None,
		parent=None,
	):
		# adjust rect so that top-left is (0.0, 0.0)
		pos = rect.topLeft()
		rect = QRectF(rect.topLeft() - rect.topLeft(), rect.bottomRight() - rect.topLeft())
		super().__init__(rect, parent)
		self.setPos(pos)
		self.label_id = label_id
		self.metadata: Dict[str, Any] = dict(metadata or {})
		self.plane_id = plane_id
		self.setZValue(9999)
		self.setFlags(
			QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
			| QGraphicsItem.GraphicsItemFlag.ItemIsMovable
			| QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
		)
		self.setAcceptHoverEvents(True)
		self._resizing = False
		self._resizing_handle = self.Sides.NONE

		self._press_rect = QRectF()
		self._press_anchor = QPointF()
		self._plane_dragging = False
		self._plane_press_uv = QPointF()
		self._plane_start_uv: list[QPointF] = []


	def load(self, data: Dict):
		super().load(data)
		self.setPos(self.fromU(data["u"]), self.fromV(data["v"]))
		self.setRect(QRectF(0, 0, self.fromU(data["width"]), self.fromV(data["height"])))
		raw_label_id = data.get("label_id")
		self.label_id = raw_label_id.strip() if isinstance(raw_label_id, str) and raw_label_id.strip() else None
		if self.label_id is None:
			legacy_name = data.get("label", "")
			label_set = self.app().labelSet()
			label = label_set.label_named(legacy_name) if label_set is not None and isinstance(legacy_name, str) else None
			self.label_id = label.id if label is not None else None
		raw_metadata = data.get("metadata", {})
		self.metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
		self.plane_id = data.get("plane_id")


	def dump(self) -> Dict:
		return super().dump() | {
			"u": self.u(),
			"v": self.v(),
			"width": self.toU(self.rect().width()),
			"height": self.toV(self.rect().height()),
			"label_id": self.label_id,
			"metadata": dict(self.metadata),
			"plane_id": self.plane_id,
		}


	def _startPlaneDrag(self, event: QGraphicsSceneMouseEvent) -> bool:
		plane = self.app().perspectivePlanes().get(self.plane_id)
		if plane is None:
			return False
		size = self.frameSize()
		try:
			self._plane_press_uv = plane.imageToPlane(event.scenePos(), size)
			rect = QRectF(self.pos(), self.rect().size())
			points = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
			self._plane_start_uv = [plane.imageToPlane(point, size) for point in points]
		except np.linalg.LinAlgError:
			return False
		if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
			self.scene().clearSelection()  # type: ignore
		self.setSelected(True)
		self._plane_dragging = True
		event.accept()
		return True


	def _moveOnPlane(self, scene_pos: QPointF) -> None:
		plane = self.app().perspectivePlanes().get(self.plane_id)
		if plane is None:
			return
		size = self.frameSize()
		try:
			current_uv = plane.imageToPlane(scene_pos, size)
			delta = current_uv - self._plane_press_uv
			points = [plane.planeToImage(point + delta, size) for point in self._plane_start_uv]
		except np.linalg.LinAlgError:
			return
		left = min(point.x() for point in points)
		right = max(point.x() for point in points)
		top = min(point.y() for point in points)
		bottom = max(point.y() for point in points)
		self.prepareGeometryChange()
		self.setPos(left, top)
		self.setRect(QRectF(0.0, 0.0, max(self.MIN_SIZE, right - left), max(self.MIN_SIZE, bottom - top)))


	def currentState(self) -> State:
		return self.State(
			self.u(),
			self.v(),
			self.toU(self.rect().width()),
			self.toV(self.rect().height())
		)


	def setState(self, data: State):
		self.prepareGeometryChange()
		self.setUvPos(data.u, data.v)
		self.setRect(QRectF(0, 0, self.fromU(data.width), self.fromV(data.height)))


	def boundingRect(self) -> QRectF:
		offset = int(math.ceil(self.SHADOW_WIDTH/2))
		return super().boundingRect().adjusted(-offset, -offset, offset, offset)


	def _handleAt(self, view: QGraphicsView, pos: QPointF):
		left, top, bottom, right = self.rect().left(), self.rect().top(), self.rect().bottom(), self.rect().right()

		if not self.rect().contains(pos):
			return self.Sides.NONE

		# Compute the effective handle point size. It should be at least MIN_HANDLE_SIZE, otherwise the HANDLE_SIZE
		handle_size = self.HANDLE_SIZE / view.transform().m11()

		handle = self.Sides.NONE
		if pos.x() - left < handle_size:
			handle |= self.Sides.W
		if right - pos.x() < handle_size:
			handle |= self.Sides.E
			if handle & self.Sides.W:
				if pos.x() - left < right - pos.x():
					handle &= ~self.Sides.E
				else:
					handle &= ~self.Sides.W
		if pos.y() - top < handle_size:
			handle |= self.Sides.N
		if bottom - pos.y() < handle_size:
			handle |= self.Sides.S
			if handle & self.Sides.N:
				if pos.y() - top < bottom - pos.y():
					handle &= ~self.Sides.S
				else:
					handle &= ~self.Sides.N
		return handle


	def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
		if event.modifiers() in (
			Qt.KeyboardModifier.NoModifier,
			Qt.KeyboardModifier.ShiftModifier
		):
			view: QGraphicsView = event.widget().parent() # type: ignore
			handle = self._handleAt(view, event.pos())
			self.setCursor(self.CURSORS[handle])
		else:
			self.setCursor(Qt.CursorShape.ArrowCursor)
		super().hoverMoveEvent(event)


	def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
		self._press_rect = QRectF(self.pos(), self.rect().size())
		self._press_anchor = event.scenePos()
		if (
			event.button() == Qt.MouseButton.LeftButton
			and event.modifiers() in (
				Qt.KeyboardModifier.NoModifier,
				Qt.KeyboardModifier.ShiftModifier
			)
		):
			view: QGraphicsView = event.widget().parent() # type: ignore
			handle = self._handleAt(view, event.pos())
			if handle != self.Sides.NONE:
				self._resizing = True
				self._resizing_handle = handle
				if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
					self.scene().clearSelection() # type: ignore
				self.setSelected(True)
				event.accept()
				return
			if self._startPlaneDrag(event):
				return
		super().mousePressEvent(event)


	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		if self._plane_dragging:
			self._moveOnPlane(event.scenePos())
			event.accept()
			return
		if self._resizing: # type: ignore
			delta = event.scenePos() - self._press_anchor
			rect = QRectF(self._press_rect)

			if self._resizing_handle & self.Sides.W:
				new_left = self._press_rect.left() + delta.x()
				rect.setLeft(min(new_left, self._press_rect.right() - self.MIN_SIZE))
			if self._resizing_handle & self.Sides.E:
				new_right = self._press_rect.right() + delta.x()
				rect.setRight(max(new_right, self._press_rect.left() + self.MIN_SIZE))
			if self._resizing_handle & self.Sides.N:
				new_top = self._press_rect.top() + delta.y()
				rect.setTop(min(new_top, self._press_rect.bottom() - self.MIN_SIZE))
			if self._resizing_handle & self.Sides.S:
				new_bottom = self._press_rect.bottom() + delta.y()
				rect.setBottom(max(new_bottom, self._press_rect.top() + self.MIN_SIZE))

			self.prepareGeometryChange()
			self.setPos(rect.topLeft())
			self.setRect(QRectF(0, 0, rect.width(), rect.height()))
			event.accept()
			return
		super().mouseMoveEvent(event)


	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
		current_rect = QRectF(self.pos(), self.rect().size())
		if self._press_rect != current_rect:
			self.scene().geometryChanged.emit() # type: ignore
		if self._resizing:
			self._resizing = False
			self._resizing_handle = self.Sides.NONE
			event.accept()
			return
		if self._plane_dragging:
			self._plane_dragging = False
			event.accept()
			return
		super().mouseReleaseEvent(event)


	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
		# draw black outline
		outline_pen = QPen()
		outline_pen.setCosmetic(True)
		for width in range(self.SHADOW_WIDTH, 0, -2):
			alpha = int(200 * (1.0 - (width / self.SHADOW_WIDTH)))
			outline_pen.setColor(QColor(0, 0, 0, alpha))
			outline_pen.setWidth(width)
			painter.setPen(outline_pen)
			painter.drawRect(self.rect())
		pen = QPen()
		pen.setWidth(2)
		brush = None
		if option.state & QStyle.StateFlag.State_Selected:
			# brush = QColor(0, 255, 0, 24)
			pen.setStyle(Qt.PenStyle.DashLine)

		label = self.resolvedLabel()
		color = QColor(label.color) if label is not None else QColor(192, 192, 192)
		if self.isInterpolated():
			color = QColor(0, 0, 255)
		elif self.isKeyframed():
			if self.currentState() == self.stateForFrame():
				color = QColor(0, 255, 0)
			else:
				color = QColor(255, 255, 0)
		if self.hasDeadLabel() and not (self.isInterpolated() or self.isKeyframed()):
			pen.setStyle(Qt.PenStyle.DashLine)
		pen.setColor(color)
		pen.setCosmetic(True)

		painter.setPen(pen)
		if brush is not None:
			painter.setBrush(brush)
		painter.drawRect(self.rect())

		# if option.state & QStyle.StateFlag.State_MouseOver:
		# 	painter.save()
		# 	pen = QPen(QColor(255, 255, 0), 1)
		# 	pen.setCosmetic(True)
		# 	painter.setPen(pen)

		# 	top, left, bottom, right = self.rect().top(), self.rect().left(), self.rect().bottom(), self.rect().right()

		# 	# Corners
		# 	painter.drawRect(QRectF(left, top, self.HANDLE_SIZE, self.HANDLE_SIZE))
		# 	painter.drawRect(QRectF(right - self.HANDLE_SIZE, top, self.HANDLE_SIZE, self.HANDLE_SIZE))
		# 	painter.drawRect(QRectF(left, bottom - self.HANDLE_SIZE, self.HANDLE_SIZE, self.HANDLE_SIZE))
		# 	painter.drawRect(QRectF(right - self.HANDLE_SIZE, bottom - self.HANDLE_SIZE, self.HANDLE_SIZE, self.HANDLE_SIZE))

		# 	# Edge
		# 	center = self.rect().center()
		# 	if self.rect().height() > 3*self.HANDLE_SIZE:
		# 		painter.drawRect(QRectF(left, center.y() - self.HANDLE_SIZE/2, self.HANDLE_SIZE, self.HANDLE_SIZE))
		# 		painter.drawRect(QRectF(right - self.HANDLE_SIZE, center.y() - self.HANDLE_SIZE/2, self.HANDLE_SIZE, self.HANDLE_SIZE))
		# 	if self.rect().width() > 3*self.HANDLE_SIZE:
		# 		painter.drawRect(QRectF(center.x() - self.HANDLE_SIZE/2, top, self.HANDLE_SIZE, self.HANDLE_SIZE))
		# 		painter.drawRect(QRectF(center.x() - self.HANDLE_SIZE/2, bottom - self.HANDLE_SIZE, self.HANDLE_SIZE, self.HANDLE_SIZE))

		# 	painter.restore()

	def __hash__(self):
		return hash(id(self))


	def __eq__(self, other):
		return id(self) == id(other)


class ObjectDetectionActivity(PerspectivePlaneActivity):

	IDENTIFIER = "Object Detection"

	def __init__(self, parent = None) -> None:
		super().__init__(parent)
		self._create_box_item = QGraphicsRectItem()
		self._create_box_item.setPen(QPen(QColor(255, 255, 0), 1))
		self._create_box_item.setBrush(QColor(255, 255, 0, 128))
		self._create_box_item.setZValue(9999)
		self._is_creating = False


	def createBox(self, rect: QRectF, select: bool = True):
		box = BoxItem(rect)
		self.addItem(box)
		if select:
			box.setSelected(True)
		self.changed.emit()


	def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
			self._is_creating = True
			self._create_box_item.setRect(QRectF(event.scenePos(), event.scenePos()))
			self.addItem(self._create_box_item)
			if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
				self.clearSelected()
			event.accept()
			return
		super().mousePressEvent(event)


	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating:
			self._create_box_item.setRect(QRectF(self._create_box_item.rect().topLeft(), event.scenePos()).normalized())
			event.accept()
			return
		super().mouseMoveEvent(event)


	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating:
			self.removeItem(self._create_box_item)
			if self._create_box_item.rect().width() < 3 or self._create_box_item.rect().height() < 3:
				return
			self.createBox(self._create_box_item.rect())
			self._is_creating = False
			event.accept()
			return
		super().mouseReleaseEvent(event)
