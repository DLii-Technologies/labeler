from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from sortedcontainers import SortedDict
import sys
from typing import cast, Dict, Generic, List, Optional, Tuple, TYPE_CHECKING, TypeVar
from PyQt6.QtCore import (
	QPointF,
	QSize,
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

if TYPE_CHECKING:
	from ..application import Application

T = TypeVar("T", bound=Dict)
@dataclass(frozen=True)
class Keyframe(Generic[T]):
	index: int
	data: T

	def __getitem__(self, key: str):
		return self.data[key]


class ActivityGraphicsItem(QGraphicsItem):
	"""
	A generic QGraphicsItem that provides methods for interfacing with activities.
	"""

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def app(self) -> Application:
		from ..application import Application
		return Application.instance()

	def frameSize(self) -> QSize:
		return self.app().mediaManager().currentFrame().size()

	def u(self) -> float:
		return self.x() / self.frameSize().width()

	def v(self) -> float:
		return self.y() / self.frameSize().height()

	def setU(self, u: float) -> None:
		self.setX(u * self.frameSize().width())

	def setV(self, v: float) -> None:
		self.setY(v * self.frameSize().height())

	def setUvPos(self, u: float, v: float) -> None:
		self.setU(u)
		self.setV(v)

	def toU(self, pixels: float) -> float:
		return pixels / self.frameSize().width()

	def toV(self, pixels: float) -> float:
		return pixels / self.frameSize().height()

	def toUv(self, pixels: QPointF) -> QPointF:
		return QPointF(self.toU(pixels.x()), self.toV(pixels.y()))

	def fromU(self, u: float) -> float:
		return u * self.frameSize().width()

	def fromV(self, v: float) -> float:
		return v * self.frameSize().height()

	def fromUv(self, uv: QPointF) -> QPointF:
		return QPointF(self.fromU(uv.x()), self.fromV(uv.y()))

class SaveableGraphicsItem(ActivityGraphicsItem):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

	def load(self, data: Dict) -> None:
		pass

	def dump(self) -> Dict:
		return {}


class KeyframeableGraphicsItem(SaveableGraphicsItem, Generic[T]):

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)

		from ..application import Application
		self._app = Application.instance()
		self._app.mediaManager().frameIndexChanged.connect(self.onFrameChanged)

		self._keyframes: Dict[int, Keyframe[T]] = SortedDict()

	# User methods ---------------------------------------------------------------------------------

	def currentState(self) -> T:
		raise NotImplementedError


	def setState(self, state: T) -> None:
		raise NotImplementedError


	def interpolateState(self, start: T, end: T, progress: float) -> T:
		if isinstance(start, dict):
			return self._interpolateDict(start, end, progress)
		if is_dataclass(start):
			return self._interpolateDataclass(start, end, progress)
		raise ValueError(f"Unsupported keyframe data type: {type(start)}")


	def _interpolateDict(self, start: T, end: T, progress: float) -> T:
		return {
			k: v + (progress * (end[k] - v))
			for k, v in start.items() # type: ignore
		}


	def _interpolateDataclass(self, start: T, end: T, progress: float) -> T:
		cls = type(start)
		return cls(**{
			field.name: getattr(start, field.name) + (progress * (getattr(end, field.name) - getattr(start, field.name)))
			for field in fields(cls) # type: ignore
		})

	# ----------------------------------------------------------------------------------------------

	def currentFrameIndex(self) -> int:
		return self._app.mediaManager().currentFrameIndex()


	def keyframeRange(self) -> Optional[Tuple[int, int]]:
		if len(self._keyframes) == 0:
			return None
		# Clamp keyframe
		left = cast(int, cast(SortedDict, self._keyframes).peekitem(0)[0])
		right = cast(int, cast(SortedDict, self._keyframes).peekitem(-1)[0])
		return left, right


	def isAlive(self, frame_index: Optional[int] = None) -> bool:
		return self.isKeyframed(frame_index) or self.isInterpolated(frame_index)


	def isInterpolated(self, frame_index: Optional[int] = None) -> bool:
		if frame_index is None:
			frame_index = self.currentFrameIndex()
		if frame_index in self._keyframes:
			return False
		keyframeRange = self.keyframeRange()
		if keyframeRange is None:
			return False
		return keyframeRange[0] <= frame_index <= keyframeRange[1]


	def isKeyframed(self, frame_index: Optional[int] = None) -> bool:
		if frame_index is None:
			frame_index = self.currentFrameIndex()
		return frame_index in self._keyframes


	def insertKeyframe(self) -> None:
		index = self.currentFrameIndex()
		state = self.currentState()
		self._keyframes[index] = Keyframe(index, state)


	def removeKeyframe(self, frame_index: Optional[int] = None) -> bool:
		if frame_index is None:
			frame_index = self.currentFrameIndex()
		if frame_index not in self._keyframes:
			return False
		del self._keyframes[frame_index]
		return True


	def stateForFrame(self, frame_index: Optional[int] = None) -> T:
		"""
		Get the state for the given frame index. If no frame index is provided,
		the current frame index is used.
		"""
		if len(self._keyframes) == 0:
			return self.currentState()

		# Clamp keyframe index
		left, right = cast(Tuple[int, int], self.keyframeRange())
		frame_index = frame_index if frame_index is not None else self.currentFrameIndex()
		frame_index = min(max(frame_index, left), right)

		if frame_index in self._keyframes:
			return self._keyframes[frame_index].data

		prev_keyframe = None
		next_keyframe = None
		for keyframe in self._keyframes.values():
			if keyframe.index < frame_index:
				prev_keyframe = keyframe
			else:
				next_keyframe = keyframe
				break
		assert prev_keyframe is not None and next_keyframe is not None
		progress = (frame_index - prev_keyframe.index) / (next_keyframe.index - prev_keyframe.index)
		return self.interpolateState(prev_keyframe.data, next_keyframe.data, progress)


	def onFrameChanged(self, frame_index: int) -> None:
		if len(self._keyframes) == 0:
			return
		state = self.stateForFrame(frame_index)
		self.setState(state)

		if not self.isAlive() and not self.isSelected():
			self.hide()
		else:
			self.show()


	def load(self, data: Dict) -> None:
		super().load(data)
		self._keyframes = SortedDict({
			index: Keyframe(index, data)
			for index, data in data.get("keyframes", [])
		})
		self.onFrameChanged(self.currentFrameIndex())


	def dump(self) -> Dict:
		return super().dump() | {
			"keyframes": [
				(keyframe.index, keyframe.data)
				for keyframe in self._keyframes.values()
			]
		}


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
		data_store = self._app.dataStore()
		if data_store is None:
			return
		self.load(data_store.get(self.IDENTIFIER))


	def _save(self) -> None:
		data_store = self._app.dataStore()
		if data_store is None:
			return
		data_store.set(self.IDENTIFIER, self.dump())


	def clear(self) -> None:
		for item in self.items():
			if item != self._frame:
				self.removeItem(item)


	def load(self, data: Optional[Dict]) -> None:
		self.clear()
		if data is None:
			return
		for module, name, data in data.get("items", []):
			item = getattr(sys.modules[module], name)()
			self.addItem(item)
			item.load(data)


	def dump(self) -> Dict:
		return {
			"items": [
				(item.__module__, item.__class__.__name__, item.dump())
				for item in self.items() if isinstance(item, SaveableGraphicsItem)
			]
		}

	def setPixmap(self, image: QPixmap) -> None:
		self._frame.setPixmap(image)


	def repaint(self) -> None:
		for item in self.items():
			item.update()

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
		if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
			self.deleteSelected()
			event.accept()
			return
		if event.key() == Qt.Key.Key_I:
			self.insertKeyframe()
			event.accept()
			return
		elif event.key() == Qt.Key.Key_X:
			self.removeKeyframe()
			event.accept()
			return
		super().keyPressEvent(event)

	# Operations -----------------------------------------------------------------------------------

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


	def deleteSelected(self) -> None:
		deleted = False
		for item in self.selectedItems():
			self.removeItem(item)
			deleted = True
		if deleted:
			self.changed.emit()
			self.repaint()


	def insertKeyframe(self) -> None:
		inserted = False
		for item in self.selectedItems():
			if isinstance(item, KeyframeableGraphicsItem):
				item.insertKeyframe()
				inserted = True
		if inserted:
			self.changed.emit()
			self.repaint()


	def removeKeyframe(self) -> None:
		removed = False
		for item in self.selectedItems():
			if isinstance(item, KeyframeableGraphicsItem):
				item.removeKeyframe()
				removed = True
		if removed:
			self.changed.emit()
			self.repaint()
