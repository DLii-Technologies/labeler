from dataclasses import dataclass
import math
import numpy as np
from typing import Dict, List

from PyQt6.QtCore import (
	QPointF,
	QRectF,
	Qt
)
from PyQt6.QtGui import (
	QBrush,
	QColor,
	QKeyEvent,
	QPainter,
	QPainterPath,
	QPainterPathStroker,
	QPen
)
from PyQt6.QtWidgets import (
	QGraphicsEllipseItem,
	QGraphicsItem,
	QGraphicsPathItem,
	QGraphicsSceneHoverEvent,
	QGraphicsSceneMouseEvent,
	QGraphicsView,
	QStyle,
	QStyleOptionGraphicsItem,
)

from . import Activity, KeyframeableGraphicsItem, SaveableGraphicsItem


class PathItem(QGraphicsPathItem, KeyframeableGraphicsItem, SaveableGraphicsItem):

	MIN_HANDLE_MARGIN = 6
	HANDLE_SIZE = 6
	SHADOW_WIDTH = 16
	MIN_POINTS = 3
	EDGE_HIT_WIDTH = 10.0

	@dataclass
	class State:
		u: float
		v: float
		points: List[tuple[float, float]]
		point_ids: list[int]
		closed: bool

	def __init__(self, points: List[QPointF] | None = None, label: str = "", parent=None):
		super().__init__(parent)
		self.label = label
		self.closed = True
		self.points: List[QPointF] = [QPointF(p) for p in (points or [])]
		self.point_ids: list[int] = list(range(len(self.points)))
		self._next_point_id = max(self.point_ids, default=-1) + 1

		self.setZValue(9999)
		self.setFlags(
			QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
			| QGraphicsItem.GraphicsItemFlag.ItemIsMovable
			| QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
		)
		self.setAcceptHoverEvents(True)

		self._dragging_point_index: int | None = None
		self._press_points: List[QPointF] = []
		self._press_scene_pos = QPointF()

		self._rebuildPath()

	def _rebuildPath(self):
		path = QPainterPath()
		if self.points:
			path.moveTo(self.points[0])
			for pt in self.points[1:]:
				path.lineTo(pt)
			if len(self.points) >= self.MIN_POINTS:
				path.closeSubpath()
		self.setPath(path)

	def _handleSizeScene(self, view: QGraphicsView) -> float:
		return self.HANDLE_SIZE / view.transform().m11()

	def _vertexAt(self, view: QGraphicsView, pos: QPointF) -> int | None:
		if not self.points:
			return None

		handle_size = self._handleSizeScene(view)
		best_index = None
		best_dist2 = None

		for i, pt in enumerate(self.points):
			dx = pos.x() - pt.x()
			dy = pos.y() - pt.y()
			dist2 = dx * dx + dy * dy
			if dist2 <= handle_size * handle_size:
				if best_dist2 is None or dist2 < best_dist2:
					best_index = i
					best_dist2 = dist2

		return best_index

	def _distancePointToSegment2(self, p: QPointF, a: QPointF, b: QPointF) -> tuple[float, QPointF]:
		abx = b.x() - a.x()
		aby = b.y() - a.y()
		apx = p.x() - a.x()
		apy = p.y() - a.y()

		ab2 = abx * abx + aby * aby
		if ab2 == 0.0:
			dx = p.x() - a.x()
			dy = p.y() - a.y()
			return dx * dx + dy * dy, QPointF(a)

		t = max(0.0, min(1.0, (apx * abx + apy * aby) / ab2))
		proj = QPointF(a.x() + t * abx, a.y() + t * aby)

		dx = p.x() - proj.x()
		dy = p.y() - proj.y()
		return dx * dx + dy * dy, proj

	def _edgeAt(self, view: QGraphicsView, pos: QPointF) -> tuple[int, QPointF] | None:
		if len(self.points) < 2:
			return None

		hit_width = self.EDGE_HIT_WIDTH / view.transform().m11()
		best = None
		best_dist2 = None

		count = len(self.points)
		for i in range(count):
			a = self.points[i]
			b = self.points[(i + 1) % count]
			dist2, proj = self._distancePointToSegment2(pos, a, b)
			if dist2 <= hit_width * hit_width:
				if best_dist2 is None or dist2 < best_dist2:
					best = (i, proj)  # insert after i
					best_dist2 = dist2

		return best

	def load(self, data: Dict):
		super().load(data)
		self.setPos(self.fromU(data["u"]), self.fromV(data["v"]))
		self.label = data.get("label", "")
		self.points = [
			QPointF(self.fromU(x), self.fromV(y))
			for x, y in data["points"]
		]
		self.closed = True
		self._rebuildPath()

	def dump(self) -> Dict:
		return super().dump() | {
			"u": self.u(),
			"v": self.v(),
			"points": [(self.toU(p.x()), self.toV(p.y())) for p in self.points],
			"label": self.label,
		}

	def currentState(self) -> State:
		return self.State(
			u=self.u(),
			v=self.v(),
			points=[(self.toU(p.x()), self.toV(p.y())) for p in self.points],
			point_ids=list(self.point_ids),
			closed=True,
		)

	def setState(self, data: State):
		self.prepareGeometryChange()
		self.setUvPos(data.u, data.v)
		self.points = [QPointF(self.fromU(x), self.fromV(y)) for x, y in data.points]
		self.point_ids = list(data.point_ids)
		self.closed = True
		self._next_point_id = max(self.point_ids, default=-1) + 1
		self._rebuildPath()

	def _mergeCyclicVertexOrder(self, start_ids: list[int], end_ids: list[int]) -> list[int]:
		common = [pid for pid in start_ids if pid in set(end_ids)]
		if len(common) < 2:
			# fallback
			seen = set()
			merged = []
			for pid in start_ids + end_ids:
				if pid not in seen:
					seen.add(pid)
					merged.append(pid)
			return merged

		start_pos = {pid: i for i, pid in enumerate(start_ids)}
		end_pos = {pid: i for i, pid in enumerate(end_ids)}
		common_set = set(common)

		anchors = common

		def collect_between(ids: list[int], a: int, b: int, allowed: set[int]) -> list[int]:
			n = len(ids)
			out = []
			i = (a + 1) % n
			while i != b:
				if ids[i] in allowed:
					out.append(ids[i])
				i = (i + 1) % n
			return out

		merged: list[int] = []
		for i, anchor in enumerate(anchors):
			next_anchor = anchors[(i + 1) % len(anchors)]

			if not merged:
				merged.append(anchor)

			start_between = collect_between(
				start_ids, start_pos[anchor], start_pos[next_anchor], set(start_ids) - common_set
			)
			end_between = collect_between(
				end_ids, end_pos[anchor], end_pos[next_anchor], set(end_ids) - common_set
			)

			merged.extend(start_between)
			merged.extend(end_between)
			merged.append(next_anchor)

		# remove duplicated final first-anchor
		if merged and merged[0] == merged[-1]:
			merged.pop()

		return merged

	def _birthSourcePoint(self, pid: int, start: State, end: State) -> tuple[float, float]:
		prev_id, next_id, t = self._neighborBracketAndT(pid, end.point_ids, end.points, set(start.point_ids))

		start_pts = {vid: pt for vid, pt in zip(start.point_ids, start.points)}
		ax, ay = start_pts[prev_id]
		bx, by = start_pts[next_id]
		return (ax + (bx - ax) * t, ay + (by - ay) * t)

	def _deathTargetPoint(self, pid: int, start: State, end: State) -> tuple[float, float]:
		prev_id, next_id, t = self._neighborBracketAndT(pid, start.point_ids, start.points, set(end.point_ids))

		end_pts = {vid: pt for vid, pt in zip(end.point_ids, end.points)}
		ax, ay = end_pts[prev_id]
		bx, by = end_pts[next_id]
		return (ax + (bx - ax) * t, ay + (by - ay) * t)

	def _neighborBracketAndT(
		self,
		pid: int,
		ids: list[int],
		points: list[tuple[float, float]],
		surviving_ids: set[int],
	) -> tuple[int, int, float]:
		n = len(ids)
		index = ids.index(pid)

		# walk backward to previous surviving vertex
		prev_index = (index - 1) % n
		while ids[prev_index] not in surviving_ids:
			prev_index = (prev_index - 1) % n
			if prev_index == index:
				raise ValueError("No surviving previous neighbor found.")

		# walk forward to next surviving vertex
		next_index = (index + 1) % n
		while ids[next_index] not in surviving_ids:
			next_index = (next_index + 1) % n
			if next_index == index:
				raise ValueError("No surviving next neighbor found.")

		prev_id = ids[prev_index]
		next_id = ids[next_index]

		# parameterize along the chain from prev_index to next_index
		chain_indices = [prev_index]
		i = (prev_index + 1) % n
		while i != next_index:
			chain_indices.append(i)
			i = (i + 1) % n
		chain_indices.append(next_index)

		def dist(a: tuple[float, float], b: tuple[float, float]) -> float:
			dx = b[0] - a[0]
			dy = b[1] - a[1]
			return (dx * dx + dy * dy) ** 0.5

		total = 0.0
		for a, b in zip(chain_indices[:-1], chain_indices[1:]):
			total += dist(points[a], points[b])

		if total <= 1e-12:
			return prev_id, next_id, 0.5

		partial = 0.0
		for a, b in zip(chain_indices[:-1], chain_indices[1:]):
			if b == index:
				partial += dist(points[a], points[b])
				break
			partial += dist(points[a], points[b])

		t = max(0.0, min(1.0, partial / total))
		return prev_id, next_id, t

	def interpolateState(self, start: State, end: State, progress: float) -> State:
		progress = max(0.0, min(1.0, progress))

		if progress <= 0.0:
			return start
		if progress >= 1.0:
			return end

		def lerp(a: float, b: float) -> float:
			return a + (b - a) * progress

		start_pts = {pid: pt for pid, pt in zip(start.point_ids, start.points)}
		end_pts = {pid: pt for pid, pt in zip(end.point_ids, end.points)}

		start_ids = list(start.point_ids)
		end_ids = list(end.point_ids)

		common_ids = [pid for pid in start_ids if pid in end_pts]
		if len(common_ids) < 2:
			# Fallback: no stable topology anchor. Best effort only.
			if len(start.points) != len(end.points):
				raise ValueError("Cannot interpolate path states: not enough shared vertex ids.")
			return self.State(
				u=lerp(start.u, end.u),
				v=lerp(start.v, end.v),
				points=[
					(lerp(sx, ex), lerp(sy, ey))
					for (sx, sy), (ex, ey) in zip(start.points, end.points)
				],
				point_ids=list(start.point_ids),
				closed=True,
			)

		merged_ids = self._mergeCyclicVertexOrder(start_ids, end_ids)

		points = []
		for pid in merged_ids:
			if pid in start_pts and pid in end_pts:
				sx, sy = start_pts[pid]
				ex, ey = end_pts[pid]
				points.append((lerp(sx, ex), lerp(sy, ey)))
			elif pid in end_pts:
				# vertex birth: source is a point on the corresponding start edge
				ex, ey = end_pts[pid]
				sx, sy = self._birthSourcePoint(pid, start, end)
				points.append((lerp(sx, ex), lerp(sy, ey)))
		else:
				# vertex death: target is a point on the corresponding end edge
				sx, sy = start_pts[pid]
				ex, ey = self._deathTargetPoint(pid, start, end)
				points.append((lerp(sx, ex), lerp(sy, ey)))

		# remove consecutive duplicates / near-duplicates caused by progress near 0 or 1
		filtered_ids: list[int] = []
		filtered_points: list[tuple[float, float]] = []
		eps2 = 1e-12
		for pid, pt in zip(merged_ids, points):
			if not filtered_points:
				filtered_ids.append(pid)
				filtered_points.append(pt)
				continue
			dx = pt[0] - filtered_points[-1][0]
			dy = pt[1] - filtered_points[-1][1]
			if dx * dx + dy * dy > eps2:
				filtered_ids.append(pid)
				filtered_points.append(pt)

		# if first and last collapse together, drop the last
		if len(filtered_points) >= 2:
			dx = filtered_points[0][0] - filtered_points[-1][0]
			dy = filtered_points[0][1] - filtered_points[-1][1]
			if dx * dx + dy * dy <= eps2:
				filtered_ids.pop()
				filtered_points.pop()

		if len(filtered_points) < self.MIN_POINTS:
			# last-resort fallback: snap to whichever side is closer
			return start if progress < 0.5 else end

		return self.State(
			u=lerp(start.u, end.u),
			v=lerp(start.v, end.v),
			points=filtered_points,
			point_ids=filtered_ids,
			closed=True,
		)

	def boundingRect(self) -> QRectF:
		offset = int(math.ceil(self.SHADOW_WIDTH / 2))
		return super().boundingRect().adjusted(-offset, -offset, offset, offset)

	def shape(self) -> QPainterPath:
		stroker = QPainterPathStroker()
		stroker.setWidth(10.0)
		return stroker.createStroke(self.path())

	def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent):
		view: QGraphicsView = event.widget().parent()  # type: ignore

		if self.isSelected():
			vertex_index = self._vertexAt(view, event.pos())
			if vertex_index is not None and event.modifiers() & Qt.KeyboardModifier.AltModifier:
				self.setCursor(Qt.CursorShape.ForbiddenCursor)
				super().hoverMoveEvent(event)
				return

			edge_hit = self._edgeAt(view, event.pos())
			meta_mod = (
				(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
				or (event.modifiers() & Qt.KeyboardModifier.MetaModifier)
			)
			if edge_hit is not None and meta_mod:
				self.setCursor(Qt.CursorShape.CrossCursor)
				super().hoverMoveEvent(event)
				return

			if vertex_index is not None and event.modifiers() in (
				Qt.KeyboardModifier.NoModifier,
				Qt.KeyboardModifier.ShiftModifier,
			):
				self.setCursor(Qt.CursorShape.CrossCursor)
				super().hoverMoveEvent(event)
				return

		self.setCursor(Qt.CursorShape.ArrowCursor)
		super().hoverMoveEvent(event)

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
		self._press_points = [QPointF(p) for p in self.points]
		self._press_scene_pos = QPointF(event.scenePos())
		self._dragging_point_index = None

		view: QGraphicsView = event.widget().parent()  # type: ignore
		vertex_index = self._vertexAt(view, event.pos())
		edge_hit = self._edgeAt(view, event.pos())

		# Alt+click vertex to delete, but only when selected and still valid after deletion.
		if (
			self.isSelected()
			and event.button() == Qt.MouseButton.LeftButton
			and (event.modifiers() & Qt.KeyboardModifier.AltModifier)
			and vertex_index is not None
		):
			if len(self.points) > self.MIN_POINTS:
				self.prepareGeometryChange()
				del self.points[vertex_index]
				del self.point_ids[vertex_index]
				self._rebuildPath()
				self.scene().changed.emit()  # type: ignore
			event.accept()
			return

		# Alt+click edge to insert, but only when selected.
		if (
			self.isSelected()
			and event.button() == Qt.MouseButton.LeftButton
			and (event.modifiers() & Qt.KeyboardModifier.AltModifier)
			and edge_hit is not None
		):
			insert_after, proj = edge_hit
			self.prepareGeometryChange()
			new_id = self._next_point_id
			self._next_point_id += 1
			self.points.insert(insert_after + 1, proj)
			self.point_ids.insert(insert_after + 1, new_id)
			self._rebuildPath()
			self.scene().changed.emit()  # type: ignore
			event.accept()
			return

		# Normal vertex drag.
		if (
			event.button() == Qt.MouseButton.LeftButton
			and event.modifiers() in (
				Qt.KeyboardModifier.NoModifier,
				Qt.KeyboardModifier.ShiftModifier,
			)
			and vertex_index is not None
		):
			self._dragging_point_index = vertex_index
			if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
				self.scene().clearSelection()  # type: ignore
			self.setSelected(True)
			event.accept()
			return

		super().mousePressEvent(event)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
		if self._dragging_point_index is not None:
			self.prepareGeometryChange()
			self.points[self._dragging_point_index] = QPointF(event.pos())
			self._rebuildPath()
			event.accept()
			return

		super().mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
		if self._dragging_point_index is not None:
			self._dragging_point_index = None
			self.scene().changed.emit()  # type: ignore
			event.accept()
			return

		if self._press_points != self.points:
			self.scene().changed.emit()  # type: ignore

		super().mouseReleaseEvent(event)

	def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
		outline_pen = QPen()
		outline_pen.setCosmetic(True)
		outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
		outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)

		for width in range(self.SHADOW_WIDTH, 0, -2):
			alpha = int(200 * (1.0 - (width / self.SHADOW_WIDTH)))
			outline_pen.setColor(QColor(0, 0, 0, alpha))
			outline_pen.setWidth(width)
			painter.setPen(outline_pen)
			painter.setBrush(Qt.BrushStyle.NoBrush)
			painter.drawPath(self.path())

		pen = QPen()
		pen.setWidth(2)
		pen.setCosmetic(True)
		pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
		pen.setCapStyle(Qt.PenCapStyle.RoundCap)

		if option.state & QStyle.StateFlag.State_Selected:
			pen.setStyle(Qt.PenStyle.DashLine)

		color = QColor(192, 192, 192)
		if self.isInterpolated():
			color = QColor(0, 0, 255)
		elif self.isKeyframed():
			if self.currentState() == self.stateForFrame():
				color = QColor(0, 255, 0)
			else:
				color = QColor(255, 255, 0)

		pen.setColor(color)
		painter.setPen(pen)
		painter.setBrush(Qt.BrushStyle.NoBrush)
		painter.drawPath(self.path())

		if option.state & QStyle.StateFlag.State_Selected:
			handle_pen = QPen(QColor(255, 255, 255))
			handle_pen.setCosmetic(True)
			painter.setPen(handle_pen)
			painter.setBrush(QColor(0, 0, 0))

			view = None
			if widget is not None and widget.parent() is not None:
				view = widget.parent()

			handle_size = self.HANDLE_SIZE
			if isinstance(view, QGraphicsView):
				handle_size = self.HANDLE_SIZE / view.transform().m11()

			r = handle_size / 2.0
			for pt in self.points:
				painter.drawRect(QRectF(pt.x() - r, pt.y() - r, handle_size, handle_size))

	def __hash__(self):
		return hash(id(self))

	def __eq__(self, other):
		return id(self) == id(other)


class ObjectSegmentationActivity(Activity):

	IDENTIFIER = "Object Segmentation"

	CLOSE_THRESHOLD = 8.0
	MIN_POINTS = 3
	START_HANDLE_SIZE = 8.0
	START_HANDLE_HOVER_SIZE = 12.0

	def __init__(self, parent=None) -> None:
		super().__init__(parent)

		self._create_path_item = QGraphicsPathItem()
		preview_pen = QPen(QColor(255, 255, 0), 2)
		preview_pen.setCosmetic(True)
		self._create_path_item.setPen(preview_pen)
		self._create_path_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
		self._create_path_item.setZValue(9999)

		self._is_creating = False
		self._create_points: list[QPointF] = []
		self._preview_pos = QPointF()
		self._hovering_start = False

		self._create_start_item = QGraphicsEllipseItem()
		self._create_start_item.setZValue(10000)
		self._updateStartHandle(hover=False)

	def _updateStartHandle(self, hover: bool):
		size = self.START_HANDLE_HOVER_SIZE if hover else self.START_HANDLE_SIZE
		pen = QPen(QColor(255, 255, 0), 2)
		pen.setCosmetic(True)
		self._create_start_item.setPen(pen)

		if hover:
			self._create_start_item.setBrush(QBrush(QColor(255, 255, 0, 180)))
		else:
			self._create_start_item.setBrush(QBrush(QColor(255, 255, 0, 80)))

		if self._create_points:
			p = self._create_points[0]
			r = size / 2.0
			self._create_start_item.setRect(QRectF(p.x() - r, p.y() - r, size, size))

	def createPath(self, points: list[QPointF], select: bool = True):
		if len(points) < self.MIN_POINTS:
			return

		origin = QPointF(points[0])
		local_points = [p - origin for p in points]

		path = PathItem(local_points)
		path.setPos(origin)

		self.addItem(path)
		if select:
			path.setSelected(True)
		self.changed.emit()

	def _distance2(self, a: QPointF, b: QPointF) -> float:
		dx = a.x() - b.x()
		dy = a.y() - b.y()
		return dx * dx + dy * dy

	def _isNearStart(self, pos: QPointF) -> bool:
		if not self._create_points:
			return False
		return self._distance2(pos, self._create_points[0]) <= self.CLOSE_THRESHOLD * self.CLOSE_THRESHOLD

	def _rebuildPreviewPath(self):
		path = QPainterPath()

		if self._create_points:
			path.moveTo(self._create_points[0])

			for pt in self._create_points[1:]:
				path.lineTo(pt)

			if self._is_creating:
				path.lineTo(self._preview_pos)

		self._create_path_item.setPath(path)
		self._updateStartHandle(self._hovering_start)

	def _finishCreate(self):
		self.removeItem(self._create_path_item)
		self.removeItem(self._create_start_item)

		points = list(self._create_points)
		self._is_creating = False
		self._create_points.clear()
		self._preview_pos = QPointF()
		self._hovering_start = False

		if len(points) < self.MIN_POINTS:
			return

		self.createPath(points)

	def _cancelCreate(self):
		if self._is_creating:
			self.removeItem(self._create_path_item)
			self.removeItem(self._create_start_item)
			self._is_creating = False
			self._create_points.clear()
			self._preview_pos = QPointF()
			self._hovering_start = False

	def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
		meta = bool(event.modifiers() & Qt.KeyboardModifier.MetaModifier)

		if event.button() == Qt.MouseButton.LeftButton:
			scene_pos = event.scenePos()

			# Start creation with Ctrl/Cmd-click.
			if not self._is_creating and (ctrl or meta):
				self._is_creating = True
				self._create_points = [scene_pos]
				self._preview_pos = scene_pos
				self._hovering_start = False
				self._rebuildPreviewPath()
				self.addItem(self._create_path_item)
				self.addItem(self._create_start_item)

				if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
					self.clearSelected()

				event.accept()
				return

			# Once creating, plain left click adds points or finishes.
			if self._is_creating:
				if len(self._create_points) >= self.MIN_POINTS and self._isNearStart(scene_pos):
					self._finishCreate()
					event.accept()
					return

				self._create_points.append(scene_pos)
				self._preview_pos = scene_pos
				self._hovering_start = (
					len(self._create_points) >= self.MIN_POINTS and
					self._isNearStart(scene_pos)
				)
				self._rebuildPreviewPath()
				event.accept()
				return

		super().mousePressEvent(event)

	def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating:
			self._preview_pos = event.scenePos()
			self._hovering_start = (
				len(self._create_points) >= self.MIN_POINTS and
				self._isNearStart(self._preview_pos)
			)
			self._rebuildPreviewPath()
			event.accept()
			return

		super().mouseMoveEvent(event)

	def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
		if self._is_creating:
			event.accept()
			return
		super().mouseReleaseEvent(event)

	def keyPressEvent(self, event: QKeyEvent) -> None:
		if self._is_creating:
			if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
				if len(self._create_points) >= self.MIN_POINTS:
					self._finishCreate()
				else:
					self._cancelCreate()
				event.accept()
				return

			if event.key() == Qt.Key.Key_Escape:
				self._cancelCreate()
				event.accept()
				return

			if event.key() == Qt.Key.Key_Backspace:
				if self._create_points:
					self._create_points.pop()
					if not self._create_points:
						self._cancelCreate()
					else:
						self._hovering_start = (
							len(self._create_points) >= self.MIN_POINTS and
							self._isNearStart(self._preview_pos)
						)
						self._rebuildPreviewPath()
				event.accept()
				return

		super().keyPressEvent(event)
