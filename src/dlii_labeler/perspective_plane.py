from __future__ import annotations

from dataclasses import dataclass
import uuid

import numpy as np
from PyQt6.QtCore import QObject, QPointF, pyqtSignal


@dataclass
class PlaneState:
	corners: list[tuple[float, float]]


def _homography(source: list[QPointF], target: list[QPointF]) -> np.ndarray:
	rows = []
	values = []
	for src, dst in zip(source, target):
		x, y = src.x(), src.y()
		u, v = dst.x(), dst.y()
		rows.append([x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y])
		values.append(u)
		rows.append([0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y])
		values.append(v)
	coefficients = np.linalg.solve(np.asarray(rows), np.asarray(values))
	return np.append(coefficients, 1.0).reshape(3, 3)


def _map(matrix: np.ndarray, point: QPointF) -> QPointF:
	result = matrix @ np.asarray([point.x(), point.y(), 1.0])
	if abs(result[2]) <= 1e-12:
		return QPointF(point)
	return QPointF(float(result[0] / result[2]), float(result[1] / result[2]))


class PerspectivePlane:
	UNIT_CORNERS = [QPointF(0.0, 0.0), QPointF(1.0, 0.0), QPointF(1.0, 1.0), QPointF(0.0, 1.0)]

	def __init__(self, plane_id: str, name: str, corners: list[tuple[float, float]]) -> None:
		self.id = plane_id
		self.name = name
		self.corners = list(corners)
		self.keyframes: dict[int, PlaneState] = {}

	def stateForFrame(self, frame_index: int) -> PlaneState:
		if not self.keyframes:
			return PlaneState(list(self.corners))
		indices = sorted(self.keyframes)
		if frame_index <= indices[0]:
			return self.keyframes[indices[0]]
		if frame_index >= indices[-1]:
			return self.keyframes[indices[-1]]
		if frame_index in self.keyframes:
			return self.keyframes[frame_index]
		left = max(index for index in indices if index < frame_index)
		right = min(index for index in indices if index > frame_index)
		progress = (frame_index - left) / (right - left)
		return PlaneState([
			(
				a[0] + (b[0] - a[0]) * progress,
				a[1] + (b[1] - a[1]) * progress,
			)
			for a, b in zip(self.keyframes[left].corners, self.keyframes[right].corners)
		])

	def setFrame(self, frame_index: int) -> None:
		self.corners = list(self.stateForFrame(frame_index).corners)

	def insertKeyframe(self, frame_index: int) -> None:
		self.keyframes[frame_index] = PlaneState(list(self.corners))

	def removeKeyframe(self, frame_index: int) -> bool:
		if frame_index not in self.keyframes:
			return False
		del self.keyframes[frame_index]
		self.setFrame(frame_index)
		return True

	def planeToImage(self, point: QPointF, frame_size) -> QPointF:
		corners = [QPointF(u * frame_size.width(), v * frame_size.height()) for u, v in self.corners]
		return _map(_homography(self.UNIT_CORNERS, corners), point)

	def imageToPlane(self, point: QPointF, frame_size) -> QPointF:
		corners = [QPointF(u * frame_size.width(), v * frame_size.height()) for u, v in self.corners]
		return _map(_homography(corners, self.UNIT_CORNERS), point)

	def dump(self) -> dict:
		return {
			"id": self.id,
			"name": self.name,
			"corners": list(self.corners),
			"keyframes": [
				(index, list(state.corners)) for index, state in sorted(self.keyframes.items())
			],
		}

	@classmethod
	def load(cls, data: dict) -> PerspectivePlane:
		plane = cls(data["id"], data.get("name", "Plane"), list(data["corners"]))
		plane.keyframes = {
			int(index): PlaneState(list(corners)) for index, corners in data.get("keyframes", [])
		}
		return plane


class PerspectivePlaneStore(QObject):
	updated = pyqtSignal()

	DATA_KEY = "perspective_planes"

	def __init__(self, app) -> None:
		super().__init__(app)
		self._app = app
		self._planes: dict[str, PerspectivePlane] = {}
		app.folderOpened.connect(self.load)
		app.mediaManager().frameIndexChanged.connect(self.setFrame)

	def all(self) -> list[PerspectivePlane]:
		return list(self._planes.values())

	def get(self, plane_id: str | None) -> PerspectivePlane | None:
		return self._planes.get(plane_id) if plane_id else None

	def create(self, corners: list[tuple[float, float]] | None = None) -> PerspectivePlane:
		plane = PerspectivePlane(
			str(uuid.uuid4()),
			f"Plane {len(self._planes) + 1}",
			corners or [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)],
		)
		self._planes[plane.id] = plane
		self.save()
		return plane

	def remove(self, plane_id: str) -> None:
		if self._planes.pop(plane_id, None) is not None:
			for activity in self._app.activities().values():
				changed = False
				for item in activity.items():
					if getattr(item, "plane_id", None) == plane_id:
						item.plane_id = None
						changed = True
				if changed:
					activity.changed.emit()
			self.save()

	def load(self, *_args) -> None:
		store = self._app.dataStore()
		data = store.get(self.DATA_KEY) if store is not None else None
		self._planes = {
			plane.id: plane
			for plane in (PerspectivePlane.load(item) for item in (data or []))
		}
		self.setFrame(self._app.mediaManager().currentFrameIndex())

	def save(self) -> None:
		store = self._app.dataStore()
		if store is not None:
			store.set(self.DATA_KEY, [plane.dump() for plane in self._planes.values()])
		self.updated.emit()

	def changed(self) -> None:
		self.save()

	def setFrame(self, frame_index: int) -> None:
		for plane in self._planes.values():
			plane.setFrame(frame_index)
		self.updated.emit()
