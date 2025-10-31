from dataclasses import dataclass
from typing import Dict
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

from . import Activity, Keyframe, KeyframeableGraphicsItem, SaveableGraphicsItem

class BoxItem(QGraphicsRectItem, KeyframeableGraphicsItem, SaveableGraphicsItem):

	MIN_HANDLE_MARGIN = 6
	HANDLE_SIZE = 6
	MIN_SIZE = 1.0

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

	def __init__(self, rect: QRectF = QRectF(), label: str = "", parent=None):
		# adjust rect so that top-left is (0.0, 0.0)
		pos = rect.topLeft()
		rect = QRectF(rect.topLeft() - rect.topLeft(), rect.bottomRight() - rect.topLeft())
		super().__init__(rect, parent)
		self.setPos(pos)
		self.label = label
		self.setZValue(9999)
		self.setFlags(
			QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
			| QGraphicsItem.GraphicsItemFlag.ItemIsMovable
			| QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
		)
		self.setAcceptHoverEvents(True)
		self._resizing = False
		self._resizing_handle = self.Sides.NONE


	def load(self, data: Dict):
		super().load(data)
		self.setPos(self.fromU(data["u"]), self.fromV(data["v"]))
		self.setRect(QRectF(0, 0, self.fromU(data["width"]), self.fromV(data["height"])))
		self.label = data["label"]


	def dump(self) -> Dict:
		return super().dump() | {
			"u": self.u(),
			"v": self.v(),
			"width": self.toU(self.rect().width()),
			"height": self.toV(self.rect().height()),
			"label": self.label
		}


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


	def _handleAt(self, view: QGraphicsView, pos: QPointF):
		left, top, bottom, right = self.rect().left(), self.rect().top(), self.rect().bottom(), self.rect().right()

		if not self.rect().contains(pos):
			return self.Sides.NONE

		# Compute the effective handle point size. It should be at least MIN_HANDLE_SIZE, otherwise the HANDLE_SIZE
		handle_size = max(self.HANDLE_SIZE / view.transform().m11(), self.MIN_HANDLE_MARGIN)

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
		self._press_rect = self.boundingRect()
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
		super().mousePressEvent(event)


	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		if self._resizing:
			delta = event.pos() - event.lastPos()
			rect = self.rect()

			if self._resizing_handle & self.Sides.W:
				new_left = self.rect().left() + delta.x()
				if self.rect().right() - new_left >= self.MIN_SIZE:
					rect.setLeft(new_left)
			elif self._resizing_handle & self.Sides.E:
				new_right = self.rect().right() + delta.x()
				if new_right - self.rect().left() >= self.MIN_SIZE:
					rect.setRight(new_right)
			if self._resizing_handle & self.Sides.N:
				new_top = self.rect().top() + delta.y()
				if self.rect().bottom() - new_top >= self.MIN_SIZE:
					rect.setTop(new_top)
			elif self._resizing_handle & self.Sides.S:
				new_bottom = self.rect().bottom() + delta.y()
				if new_bottom - self.rect().top() >= self.MIN_SIZE:
					rect.setBottom(new_bottom)

			self.prepareGeometryChange()
			self.setRect(rect)
			event.accept()
			return
		super().mouseMoveEvent(event)


	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
		if self._press_rect != self.rect():
			self.scene().changed.emit() # type: ignore
		if self._resizing:
			self._resizing = False
			self._resizing_handle = self.Sides.NONE
			event.accept()
			return
		super().mouseReleaseEvent(event)


	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
		pen = QPen()
		pen.setWidth(1)
		brush = None
		if option.state & QStyle.StateFlag.State_Selected:
			brush = QColor(0, 255, 0, 24)
			pen.setStyle(Qt.PenStyle.DashLine)

		if self.isInterpolated():
			pen.setColor(QColor(0, 0, 255))
		elif self.isKeyframed():
			pen.setColor(QColor(0, 255, 0))
		else:
			pen.setColor(QColor(192, 192, 192))
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


class ObjectDetectionActivity(Activity):

	IDENTIFIER = "Object Detection"
	...

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
