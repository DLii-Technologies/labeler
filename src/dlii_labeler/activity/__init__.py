from dataclasses import dataclass
from typing import List, Optional
from PyQt6.QtCore import (
	Qt,
	QPoint,
	QPointF,
)
from PyQt6.QtGui import (
	QColor,
	QPen,
	QPixmap
)
from PyQt6.QtWidgets import (
	QGraphicsPixmapItem,
	QGraphicsItem,
	QGraphicsRectItem,
	QGraphicsScene,
	QGraphicsSceneMouseEvent
)

class Activity(QGraphicsScene):

	IDENTIFIER = "None"
	DRAG_THRESHOLD = 5

	@dataclass
	class PressContext:
		movement: str
		screen_pos: QPoint
		scene_pos: QPointF
		button: Qt.MouseButton
		modifiers: Qt.KeyboardModifier

	def __init__(self, parent = None) -> None:
		super().__init__(parent)
		self._frame = QGraphicsPixmapItem()
		self.addItem(self._frame)

		self._mouse_press_state: Optional[Activity.PressContext] = None

		self._current_selection: set[QGraphicsItem] = set()

		self._select_box_item = QGraphicsRectItem()
		self._select_box_item.setPen(QPen(QColor(128, 128, 128), 1))
		self._select_box_item.setBrush(QColor(128, 128, 128, 128))
		self._select_box_item.setOpacity(0.5)
		self._select_box_item.setZValue(9999)
		self._is_drag_selecting = False
		self._is_object_dragging = False

	def clearSelected(self) -> None:
		for item in self.selectedItems():
			item.setSelected(False)

	def toggleSelected(self, itmes: List[QGraphicsItem]) -> None:
		for item in itmes:
			item.setSelected(not item.isSelected())

	def deselect(self, items: List[QGraphicsItem]) -> None:
		for item in items:
			item.setSelected(False)

	def select(self, items: List[QGraphicsItem], clear: bool = True) -> None:
		if clear:
			self.clearSelected()
		for item in items:
			item.setSelected(True)

	def setPixmap(self, image: QPixmap) -> None:
		self._frame.setPixmap(image)

	# Event Handling -------------------------------------------------------------------------------

	def cancelMousePress(self, ) -> None:
		if self._mouse_press_state is None:
			return
		self._mouse_press_state = None


	def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
			for item in self.items(event.scenePos()):
				if item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable:
					item.setSelected(not item.isSelected())
					event.accept()
					return
		super().mousePressEvent(event)


	def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		self.mousePressEvent(event)
