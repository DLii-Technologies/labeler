from dataclasses import dataclass
from typing import List, Optional
from PyQt6.QtCore import (
	Qt,
	QRectF,
	QPoint,
	QPointF,
)
from PyQt6.QtGui import (
	QColor,
	QPen,
	QPixmap,
	QVector2D
)
from PyQt6.QtWidgets import (
	QGraphicsPixmapItem,
	QGraphicsItem,
	QGraphicsRectItem,
	QGraphicsScene,
	QGraphicsSceneMouseEvent,
	QWidget
)

class Selectable(QGraphicsItem):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)


class GraphicsSceneMouseListener:

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self._is_mouse_dragging = False

	def isMouseDragging(self) -> bool:
		return self._is_mouse_dragging

	def cancelMousePress(self, ) -> None:
		...

	def mouseDragBeginEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		...

	def mouseDragUpdateEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		...

	def mouseDragEndEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		...

	def mouseDragCancelEvent(self, context: "Activity.PressContext") -> None:
		...

	def mouseClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		...

	def _mouseDragBeginEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		self._is_mouse_dragging = True
		self.mouseDragBeginEvent(context, event)

	def _mouseDragCancelEvent(self, context: "Activity.PressContext") -> None:
		if not self._is_mouse_dragging:
			return
		self.mouseDragCancelEvent(context)

	def _mouseDragUpdateEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if not self._is_mouse_dragging:
			return
		self.mouseDragUpdateEvent(context, event)

	def _mouseDragEndEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if not self._is_mouse_dragging:
			return
		self.mouseDragEndEvent(context, event)


class Activity(GraphicsSceneMouseListener, QGraphicsScene):

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
		self._mouse_listeners: List[GraphicsSceneMouseListener] = []
		self.registerMouseListener(self)

		self._selected: set[QGraphicsItem] = set()
		self._current_selection: set[QGraphicsItem] = set()

		self._select_box_item = QGraphicsRectItem()
		self._select_box_item.setPen(QPen(QColor(128, 128, 128), 1))
		self._select_box_item.setBrush(QColor(128, 128, 128, 128))
		self._select_box_item.setOpacity(0.5)
		self._select_box_item.setZValue(9999)
		self._is_drag_selecting = False
		self._is_object_dragging = False

	def clearSelected(self) -> None:
		for item in self._selected:
			item.setSelected(False)
		self._selected.clear()

	def toggleSelected(self, itmes: List[QGraphicsItem]) -> None:
		to_deselect = []
		to_select = []
		for item in itmes:
			if item in self._selected:
				to_deselect.append(item)
			else:
				to_select.append(item)
		self.deselect(to_deselect)
		self.select(to_select, clear = False)

	def deselect(self, items: List[QGraphicsItem]) -> None:
		for item in items:
			item.setSelected(False)
		self._selected.difference_update(items)

	def select(self, items: List[QGraphicsItem], clear: bool = True) -> None:
		if clear:
			self.clearSelected()
		self._selected.update(items)
		for item in self._selected:
			item.setSelected(True)

	def setPixmap(self, image: QPixmap) -> None:
		self._frame.setPixmap(image)

	# Event Handling -------------------------------------------------------------------------------

	def registerMouseListener(self, listener: GraphicsSceneMouseListener) -> None:
		self._mouse_listeners.append(listener)


	def cancelMousePress(self, ) -> None:
		if self._mouse_press_state is None:
			return
		if self._mouse_press_state.movement == "drag":
			self.mouseDragCancelEvent(self._mouse_press_state)
		self._mouse_press_state = None


	def mouseDragBeginEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if event.isAccepted():
			return
		if context.button == Qt.MouseButton.LeftButton and any(item.isSelected() for item in self.items(context.scene_pos)):
			# Object dragging
			self._is_object_dragging = True
			event.accept()

		elif context.button == Qt.MouseButton.LeftButton and context.modifiers == Qt.KeyboardModifier.NoModifier:
			self._select_box_item.setRect(QRectF(context.scene_pos, event.scenePos()).normalized())
			self.addItem(self._select_box_item)
			self._is_drag_selecting = True
			event.accept()


	def mouseDragUpdateEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if event.isAccepted():
			return
		if self._is_object_dragging:
			delta = event.scenePos() - event.lastScenePos()
			for item in self._selected:
				item.setPos(item.pos() + delta)
			event.accept()
		elif self._is_drag_selecting:
			self._select_box_item.setRect(QRectF(context.scene_pos, event.scenePos()).normalized())
			event.accept()


	def mouseDragEndEvent(self, context: "Activity.PressContext", event: QGraphicsSceneMouseEvent) -> None:
		if event.isAccepted():
			return
		if self._is_object_dragging:
			self._is_object_dragging = False
			event.accept()
		if self._is_drag_selecting:
			self.removeItem(self._select_box_item)
			self._is_drag_selecting = False
			event.accept()


	def mouseDragCancelEvent(self, context: "Activity.PressContext") -> None:
		if self._is_object_dragging:
			self._is_object_dragging = False
		if self._is_drag_selecting:
			self.removeItem(self._select_box_item)
			self._is_drag_selecting = False


	def mouseClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if event.button() == Qt.MouseButton.LeftButton and event.modifiers() in (
			Qt.KeyboardModifier.NoModifier,
			Qt.KeyboardModifier.ControlModifier,
			Qt.KeyboardModifier.ShiftModifier
		):
			for item in self.items(event.scenePos()):
				print("Checking", item)
				if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
					continue

				# Found an item. Now we need to figure out what to do with it.
				if event.modifiers() in (
					Qt.KeyboardModifier.ControlModifier,
					Qt.KeyboardModifier.ShiftModifier
				):
					self.toggleSelected([item])
				else:
					self.select([item], clear=True)
				break
			else:
				self.clearSelected()
			event.accept()


	def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		print("Double clicked in activity")


	def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._mouse_press_state is not None:
			for listener in self._mouse_listeners:
				listener.cancelMousePress()
			self._mouse_press_state = None
		self._mouse_press_state = self.PressContext(
			movement = "press",
			screen_pos = event.screenPos(),
			scene_pos = event.scenePos(),
			button = event.button(),
			modifiers = event.modifiers()
		)


	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._mouse_press_state is None:
			return

		if self._mouse_press_state.movement == "press":
			distance = QVector2D(event.screenPos() - self._mouse_press_state.screen_pos).length()
			if distance >= Activity.DRAG_THRESHOLD:
				self._mouse_press_state.movement = "drag"
				for listener in self._mouse_listeners:
					listener._mouseDragBeginEvent(self._mouse_press_state, event)
					if event.isAccepted():
						break

		elif self._mouse_press_state.movement == "drag":
			for listener in self._mouse_listeners:
				listener._mouseDragUpdateEvent(self._mouse_press_state, event)
				if event.isAccepted():
					break


	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._mouse_press_state is None:
			return
		if self._mouse_press_state.movement == "press" and event.button() == self._mouse_press_state.button:
			for listener in self._mouse_listeners:
				listener.mouseClickEvent(event)
				if event.isAccepted():
					break
		elif self._mouse_press_state.movement == "drag":
			for listener in self._mouse_listeners:
				listener._mouseDragEndEvent(self._mouse_press_state, event)
				if event.isAccepted():
					break
		self._mouse_press_state = None
