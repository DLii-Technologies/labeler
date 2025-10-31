import sys
from typing import Dict, List, Optional
from PyQt6.QtCore import (
	Qt,
	pyqtSignal
)
from PyQt6.QtGui import (
	QKeyEvent,
	QPixmap
)
from PyQt6.QtWidgets import (
	QGraphicsPixmapItem,
	QGraphicsItem,
	QGraphicsScene,
	QGraphicsSceneMouseEvent
)
class KeyframeableGraphicsItem(QGraphicsItem):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)


class SerializableGraphicsItem(QGraphicsItem):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	@classmethod
	def deserialize(cls, data: Dict) -> "SerializableGraphicsItem":
		raise NotImplementedError

	def serialize(self) -> Dict:
		raise NotImplementedError


class Activity(QGraphicsScene):

	IDENTIFIER = "None"
	DRAG_THRESHOLD = 5

	changed = pyqtSignal()

	def __init__(self, parent = None) -> None:
		super().__init__(parent)
		self._frame = QGraphicsPixmapItem()
		self.addItem(self._frame)

		self._current_selection: set[QGraphicsItem] = set()

		from ..application import Application
		self._app = Application.instance()
		self._app.mediaManager().frameChanged.connect(self.setPixmap)
		self._app.folderOpened.connect(self._load)
		self.changed.connect(self._save)

	def _load(self) -> None:
		self.load(self._app.dataStore().get(self.IDENTIFIER))


	def _save(self) -> None:
		self._app.dataStore().set(self.IDENTIFIER, self.dump())


	def load(self, data: Optional[Dict]) -> None:
		if data is None:
			return
		for module, name, data in data.get("items", []):
			item = getattr(sys.modules[module], name).deserialize(data)
			self.addItem(item)


	def dump(self) -> Dict:
		return {
			"items": [
				(item.__module__, item.__class__.__name__, item.serialize())
				for item in self.items() if isinstance(item, SerializableGraphicsItem)
			]
		}


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

	def keyPressEvent(self, event: QKeyEvent) -> None:
		if event.key() == Qt.Key.Key_Delete:
			for item in self.selectedItems():
				self.removeItem(item)
			event.accept()
			return
		super().keyPressEvent(event)
