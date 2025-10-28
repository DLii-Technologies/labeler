from dataclasses import dataclass
from enum import Enum
from typing import Optional
from PyQt6.QtCore import (
	QRectF,
	QPointF,
	Qt
)
from PyQt6.QtGui import (
	QColor,
	QPen
)
from PyQt6.QtWidgets import (
	QGraphicsItem,
	QGraphicsRectItem,
	QGraphicsSceneMouseEvent
)

from . import Selectable, Activity

class BoxItem(QGraphicsRectItem, Selectable):
	def __init__(self, rect: QRectF, label: str = "", parent=None):
		super().__init__(rect, parent)
		self.label = label
		self.setPen(QPen(QColor(0, 255, 0), 1))
		self.setBrush(QColor(0, 255, 0, 24))
		self.setZValue(9999)
		self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)

	def __hash__(self):
		return hash(id(self))

	def __eq__(self, other):
		return id(self) == id(other)


class ObjectDetectionActivity(Activity):

	IDENTIFIER = "Object Detection"
	...

	def __init__(self, parent = None) -> None:
		super().__init__(parent)
		self._boxes = set()

		self._create_box_item = QGraphicsRectItem()
		self._create_box_item.setPen(QPen(QColor(255, 255, 0), 1))
		self._create_box_item.setBrush(QColor(255, 255, 0, 128))
		self._create_box_item.setZValue(9999)
		self._is_creating = False

		self.createBox(QRectF(100, 100, 200, 200))


	def createBox(self, rect: QRectF):
		box = BoxItem(rect)
		self.addItem(box)
		self._boxes.add(box)


	def mouseDragBeginEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if context.button == Qt.MouseButton.LeftButton and context.modifiers == Qt.KeyboardModifier.ControlModifier:
			self._create_box_item.setRect(QRectF(context.scene_pos, event.scenePos()).normalized())
			self.addItem(self._create_box_item)
			self._is_creating = True
			event.accept()
			return
		super().mouseDragBeginEvent(context, event)


	def mouseDragUpdateEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating:
			self._create_box_item.setRect(QRectF(context.scene_pos, event.scenePos()).normalized())
			event.accept()
			return
		return super().mouseDragUpdateEvent(context, event)


	def mouseDragEndEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating:
			self.removeItem(self._create_box_item)
			self.createBox(self._create_box_item.rect())
			self._is_creating = False
			event.accept()
			return
		return super().mouseDragEndEvent(context, event)


	def mouseDragCancelEvent(self, context: "Activity.PressContext") -> None:
		if self._is_creating:
			self.removeItem(self._create_box_item)
			self._is_creating = False
			return
		return super().mouseDragCancelEvent(context)
