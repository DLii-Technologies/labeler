from __future__ import annotations

import numpy as np
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF
from PyQt6.QtWidgets import (
	QGraphicsItem,
	QGraphicsPathItem,
	QGraphicsPolygonItem,
	QGraphicsSceneHoverEvent,
	QGraphicsSceneMouseEvent,
	QGraphicsView,
	QStyle,
	QStyleOptionGraphicsItem,
)

from . import Activity
from ..perspective_plane import PerspectivePlane


class PerspectivePlaneItem(QGraphicsPolygonItem):
	HANDLE_SIZE = 9.0
	HIT_WIDTH = 10.0

	def __init__(self, plane: PerspectivePlane, parent=None) -> None:
		super().__init__(parent)
		self.plane = plane
		self._dragging_corner: int | None = None
		self.setZValue(9000)
		self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
		self.setAcceptHoverEvents(True)
		self.refresh()

	def _frameSize(self):
		from ..application import Application
		return Application.instance().mediaManager().currentFrame().size()

	def refresh(self) -> None:
		size = self._frameSize()
		if size.width() <= 0 or size.height() <= 0:
			return
		self.prepareGeometryChange()
		self.setPolygon(QPolygonF([
			QPointF(u * size.width(), v * size.height()) for u, v in self.plane.corners
		]))
		self.update()

	def _view(self, event) -> QGraphicsView:
		return event.widget().parent()  # type: ignore

	def _cornerAt(self, view: QGraphicsView, pos: QPointF) -> int | None:
		radius = self.HANDLE_SIZE / abs(view.transform().m11())
		for index, point in enumerate(self.polygon()):
			delta = pos - point
			if delta.x() * delta.x() + delta.y() * delta.y() <= radius * radius:
				return index
		return None

	def shape(self) -> QPainterPath:
		path = QPainterPath()
		path.addPolygon(self.polygon())
		stroker = QPainterPathStroker()
		stroker.setWidth(self.HIT_WIDTH)
		shape = stroker.createStroke(path)
		if self.isSelected():
			scale = 1.0
			if self.scene() is not None and self.scene().views():
				scale = max(1e-12, abs(self.scene().views()[0].transform().m11()))
			radius = self.HANDLE_SIZE / scale
			for point in self.polygon():
				shape.addEllipse(point, radius, radius)
		return shape

	def boundingRect(self) -> QRectF:
		return super().boundingRect().adjusted(-48.0, -48.0, 48.0, 48.0)

	def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
		if self.isSelected() and self._cornerAt(self._view(event), event.pos()) is not None:
			self.setCursor(Qt.CursorShape.CrossCursor)
		else:
			self.setCursor(Qt.CursorShape.ArrowCursor)
		super().hoverMoveEvent(event)

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self.isSelected() and event.button() == Qt.MouseButton.LeftButton:
			corner = self._cornerAt(self._view(event), event.pos())
			if corner is not None:
				self._dragging_corner = corner
				event.accept()
				return
		super().mousePressEvent(event)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._dragging_corner is not None:
			size = self._frameSize()
			if size.width() > 0 and size.height() > 0:
				corners = list(self.plane.corners)
				corners[self._dragging_corner] = (
					event.pos().x() / size.width(),
					event.pos().y() / size.height(),
				)
				self.plane.corners = corners
				from ..application import Application
				Application.instance().perspectivePlanes().updated.emit()
			event.accept()
			return
		super().mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._dragging_corner is not None:
			self._dragging_corner = None
			from ..application import Application
			Application.instance().perspectivePlanes().changed()
			event.accept()
			return
		super().mouseReleaseEvent(event)

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None) -> None:
		color = QColor(0, 220, 255)
		pen = QPen(color, 2)
		pen.setCosmetic(True)
		pen.setStyle(Qt.PenStyle.SolidLine if self.isSelected() else Qt.PenStyle.DashLine)
		painter.setPen(pen)
		painter.setBrush(QColor(0, 220, 255, 18))
		painter.drawPolygon(self.polygon())

		size = self._frameSize()
		if size.width() > 0 and size.height() > 0:
			grid_pen = QPen(QColor(0, 220, 255, 120), 1)
			grid_pen.setCosmetic(True)
			painter.setPen(grid_pen)
			try:
				for step in range(1, 4):
					t = step / 4.0
					painter.drawLine(
						self.plane.planeToImage(QPointF(t, 0.0), size),
						self.plane.planeToImage(QPointF(t, 1.0), size),
					)
					painter.drawLine(
						self.plane.planeToImage(QPointF(0.0, t), size),
						self.plane.planeToImage(QPointF(1.0, t), size),
					)
			except np.linalg.LinAlgError:
				pass

		if option.state & QStyle.StateFlag.State_Selected:
			painter.setPen(QPen(QColor(255, 255, 255), 1))
			painter.setBrush(color)
			view = widget.parent() if widget is not None else None
			handle_size = self.HANDLE_SIZE
			if isinstance(view, QGraphicsView):
				handle_size /= abs(view.transform().m11())
			radius = handle_size / 2.0
			for point in self.polygon():
				painter.drawEllipse(point, radius, radius)

		painter.setPen(QPen(color))
		if not self.polygon().isEmpty():
			painter.drawText(self.polygon()[0] + QPointF(6.0, -6.0), self.plane.name)


class PerspectivePlaneActivity(Activity):
	SHOW_PLANES = False

	def __init__(self, parent=None) -> None:
		super().__init__(parent)
		self._plane_items: dict[str, PerspectivePlaneItem] = {}
		self._is_creating_plane = False
		self._create_points: list[QPointF] = []
		self._create_preview_pos = QPointF()
		self._create_plane_item = QGraphicsPathItem()
		preview_pen = QPen(QColor(255, 255, 0), 2)
		preview_pen.setCosmetic(True)
		self._create_plane_item.setPen(preview_pen)
		self._create_plane_item.setBrush(QColor(255, 255, 0, 24))
		self._create_plane_item.setZValue(10000)
		self._app.perspectivePlanes().updated.connect(self._refreshPlaneItems)
		self._refreshPlaneItems()

	def _rebuildCreatePreview(self) -> None:
		path = QPainterPath()
		if self._create_points:
			path.moveTo(self._create_points[0])
			for point in self._create_points[1:]:
				path.lineTo(point)
			if self._is_creating_plane:
				path.lineTo(self._create_preview_pos)
				if len(self._create_points) >= 3:
					path.lineTo(self._create_points[0])
			for point in self._create_points:
				path.addEllipse(point, 3.0, 3.0)
		self._create_plane_item.setPath(path)

	def _cancelPlaneCreate(self) -> None:
		if self._create_plane_item.scene() is self:
			self.removeItem(self._create_plane_item)
		self._is_creating_plane = False
		self._create_points.clear()
		self._create_preview_pos = QPointF()

	def _finishPlaneCreate(self) -> None:
		points = list(self._create_points)
		self._cancelPlaneCreate()
		if len(points) != 4:
			return
		size = self._app.mediaManager().currentFrame().size()
		if size.width() <= 0 or size.height() <= 0:
			return
		plane = self._app.perspectivePlanes().create([
			(point.x() / size.width(), point.y() / size.height()) for point in points
		])
		self.clearSelected()
		self._plane_items[plane.id].setSelected(True)

	def _refreshPlaneItems(self) -> None:
		if not self.SHOW_PLANES:
			for item in self._plane_items.values():
				self.removeItem(item)
			self._plane_items.clear()
			return
		planes = {plane.id: plane for plane in self._app.perspectivePlanes().all()}
		for plane_id in list(self._plane_items):
			if plane_id not in planes:
				self.removeItem(self._plane_items.pop(plane_id))
		for plane_id, plane in planes.items():
			item = self._plane_items.get(plane_id)
			if item is None:
				item = PerspectivePlaneItem(plane)
				self._plane_items[plane_id] = item
				self.addItem(item)
			else:
				item.refresh()

	def load(self, data) -> None:
		self._cancelPlaneCreate()
		super().load(data)
		self._plane_items.clear()
		self._refreshPlaneItems()

	def deleteSelected(self) -> None:
		planes = [item for item in self.selectedItems() if isinstance(item, PerspectivePlaneItem)]
		for item in planes:
			self._app.perspectivePlanes().remove(item.plane.id)
		if any(not isinstance(item, PerspectivePlaneItem) for item in self.selectedItems()):
			super().deleteSelected()

	def insertKeyframe(self) -> None:
		frame = self._app.mediaManager().currentFrameIndex()
		planes = [item for item in self.selectedItems() if isinstance(item, PerspectivePlaneItem)]
		for item in planes:
			item.plane.insertKeyframe(frame)
		if planes:
			self._app.perspectivePlanes().changed()
		if any(not isinstance(item, PerspectivePlaneItem) for item in self.selectedItems()):
			super().insertKeyframe()

	def removeKeyframe(self) -> None:
		frame = self._app.mediaManager().currentFrameIndex()
		planes = [item for item in self.selectedItems() if isinstance(item, PerspectivePlaneItem)]
		if any(item.plane.removeKeyframe(frame) for item in planes):
			self._app.perspectivePlanes().changed()
		if any(not isinstance(item, PerspectivePlaneItem) for item in self.selectedItems()):
			super().removeKeyframe()

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		ctrl_or_meta = bool(
			event.modifiers() & (
				Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
			)
		)
		if (
			self.SHOW_PLANES
			and not self._is_creating_plane
			and event.button() == Qt.MouseButton.LeftButton
			and ctrl_or_meta
		):
			self._is_creating_plane = True
			self._create_points = [event.scenePos()]
			self._create_preview_pos = event.scenePos()
			self._rebuildCreatePreview()
			self.addItem(self._create_plane_item)
			self.clearSelected()
			event.accept()
			return

		if self._is_creating_plane and event.button() == Qt.MouseButton.LeftButton:
			self._create_points.append(event.scenePos())
			self._create_preview_pos = event.scenePos()
			if len(self._create_points) == 4:
				self._finishPlaneCreate()
			else:
				self._rebuildCreatePreview()
			event.accept()
			return

		super().mousePressEvent(event)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating_plane:
			self._create_preview_pos = event.scenePos()
			self._rebuildCreatePreview()
			event.accept()
			return
		super().mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating_plane:
			event.accept()
			return
		super().mouseReleaseEvent(event)

	def keyPressEvent(self, event: QKeyEvent) -> None:
		if self._is_creating_plane and event.key() == Qt.Key.Key_Escape:
			self._cancelPlaneCreate()
			event.accept()
			return
		if self._is_creating_plane and event.key() == Qt.Key.Key_Backspace:
			if self._create_points:
				self._create_points.pop()
			if not self._create_points:
				self._cancelPlaneCreate()
			else:
				self._rebuildCreatePreview()
			event.accept()
			return
		super().keyPressEvent(event)


class PerspectivePlaneEditorActivity(PerspectivePlaneActivity):
	IDENTIFIER = "Perspective Planes"
	SHOW_PLANES = True
