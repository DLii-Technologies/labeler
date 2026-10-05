"""Project editing transactions backed by Qt's undo stack."""

from contextlib import contextmanager, ExitStack
from copy import deepcopy
from functools import wraps
import sys

from PyQt6.QtCore import QObject, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QUndoCommand, QUndoStack


def operation(name):
	"""Group all mutations in a method (including nested operations) into one edit."""
	def decorate(method):
		@wraps(method)
		def wrapped(self, *args, **kwargs):
			from .application import Application
			history = getattr(Application.instance(), "_operations", None)
			if history is None:
				return method(self, *args, **kwargs)
			with history.operation(name):
				return method(self, *args, **kwargs)
		return wrapped
	return decorate


class EditOperation(QUndoCommand):
	def __init__(self, history, name, frame, before, after):
		super().__init__(name)
		self.history = history
		self.frame = frame
		self.before = before
		self.after = after
		self._already_applied = True

	def undo(self):
		self.history.restore(self.before, self.frame)

	def redo(self):
		# QUndoStack.push calls redo; the initial edit has already happened.
		if self._already_applied:
			self._already_applied = False
		else:
			self.history.restore(self.after, self.frame)


class OperationHistory(QObject):
	restored = pyqtSignal()

	def __init__(self, app):
		super().__init__(app)
		self.app = app
		self.stack = QUndoStack(self)
		self.stack.setUndoLimit(100)
		self._depth = 0
		self.replaying = False

	def begin(self, name):
		if self.replaying or self.app.dataStore() is None:
			return False
		if not self._depth:
			self._before = self.capture()
			self._frame = self.app.mediaManager().currentFrameIndex()
			self._name = name
		self._depth += 1
		return True

	def end(self):
		self._depth -= 1
		if self._depth:
			return
		after = self.capture()
		keys = self._before.keys() | after.keys()
		changed = [key for key in keys if self._content(self._before.get(key)) != self._content(after.get(key))]
		if changed:
			self.stack.push(EditOperation(
				self, self._name, self._frame,
				{key: self._before.get(key) for key in changed},
				{key: after.get(key) for key in changed},
			))
		self._before = None

	@contextmanager
	def operation(self, name):
		started = self.begin(name)
		try:
			yield
		finally:
			if started:
				self.end()

	@staticmethod
	def _content(record):
		# Selecting an object is UI state, not an edit, but selection is restored with edits.
		return {key: value for key, value in record.items() if key != "selected"} if isinstance(record, dict) else record

	def capture(self):
		from .activity import KeyframeableGraphicsItem
		state = {}
		for activity_id, activity in self.app.activities().items():
			selected = set(activity.selectedAnnotationItems())
			for item in activity.items():
				if isinstance(item, KeyframeableGraphicsItem):
					state[("object", activity_id, item.timeline_id)] = {
						"module": item.__module__, "class": item.__class__.__name__,
						"data": item.dump(), "selected": item in selected,
					}
		for plane in self.app.perspectivePlanes().all():
			state[("plane", plane.id)] = plane.dump()
		label_set = self.app.labelSet()
		state[("labels",)] = label_set.to_dict() if label_set is not None else None
		store = self.app.dataStore()
		layout = store.get("scrubber_layout") if store is not None else None
		if isinstance(layout, dict):
			state[("layout",)] = {
				"order": layout.get("order", []),
				"groups": [{key: value for key, value in group.items() if key != "collapsed"} for group in layout.get("groups", [])],
			}
		return deepcopy(state)

	def restore(self, changes, frame):
		from .activity import KeyframeableGraphicsItem
		from .label_sets import LabelSet
		from .perspective_plane import PerspectivePlane
		self.replaying = True
		try:
			self.app.mediaManager().setIndex(frame)
			store = self.app.dataStore()
			activities = self.app.activities()
			affected = {key[1] for key in changes if key[0] == "object"}
			planes_changed = any(key[0] == "plane" for key in changes)
			with ExitStack() as blockers:
				for activity in activities.values():
					blockers.enter_context(QSignalBlocker(activity))
				if ("labels",) in changes:
					data = changes[("labels",)]
					self.app._label_set = LabelSet.from_dict(data) if data is not None else None
					store.set("label_set", data)
					store.set("label_set_id", data["id"] if data else None)
				for key, record in changes.items():
					if key[0] == "plane":
						planes = self.app.perspectivePlanes()._planes
						if record is None:
							planes.pop(key[1], None)
						else:
							plane = PerspectivePlane.load(deepcopy(record))
							if key[1] in planes:
								planes[key[1]].__dict__.update(plane.__dict__)
							else:
								planes[key[1]] = plane
				for activity_id in affected:
					activity = activities[activity_id]
					items = {item.timeline_id: item for item in activity.items() if isinstance(item, KeyframeableGraphicsItem)}
					selected = set(activity.selectedAnnotationItems())
					for key, record in changes.items():
						if key[:2] != ("object", activity_id):
							continue
						item = items.get(key[2])
						if record is None:
							if item is not None:
								selected.discard(item)
								activity.removeItem(item)
							continue
						if item is None:
							item = getattr(sys.modules[record["module"]], record["class"])()
							activity.addItem(item)
						item.load(deepcopy(record["data"]))
						if record["selected"]:
							selected.add(item)
						else:
							selected.discard(item)
					activity.setTimelineSelection(list(selected))
			if planes_changed:
				self.app.perspectivePlanes().save()
			if ("layout",) in changes:
				layout = store.get("scrubber_layout") or {}
				collapsed = {group["id"]: group.get("collapsed", False) for group in layout.get("groups", [])}
				layout.update(deepcopy(changes[("layout",)]) or {"order": [], "groups": []})
				for group in layout["groups"]:
					group["collapsed"] = collapsed.get(group["id"], False)
				store.set("scrubber_layout", layout)
			if ("labels",) in changes:
				self.app.labelSetChanged.emit()
			for activity_id in affected:
				activities[activity_id].geometryChanged.emit()
				activities[activity_id].repaint()
			self.restored.emit()
		finally:
			self.replaying = False

	def undo(self):
		self._commitEditor()
		if not self._depth:
			self.stack.undo()

	def redo(self):
		self._commitEditor()
		if not self._depth:
			self.stack.redo()

	def _commitEditor(self):
		focused = self.app.focusWidget()
		if focused is not None:
			focused.clearFocus()
