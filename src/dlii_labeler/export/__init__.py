import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
	from ..application import Application


class UnassignedObjectsError(ValueError):

	def __init__(self, count: int):
		self.count = count
		super().__init__(f"{count} object{'s are' if count != 1 else ' is'} unassigned.")


class Exporter:

	def __init__(self):
		self._allow_unassigned = False

	def app(self) -> "Application":
		from ..application import Application
		return Application.instance()

	def export(self, options: Any) -> None:
		raise NotImplementedError

	def classIdForItem(self, item) -> int:
		label_id = getattr(item, "label_id", None)
		if label_id is None and self._allow_unassigned:
			return -1
		label_set = self.app().labelSet()
		if label_set is None:
			raise ValueError("No label set is selected for this project.")
		class_id = label_set.class_id(label_id)
		if class_id is not None:
			return class_id
		label = label_set.label(label_id)
		if label is not None:
			raise ValueError(f"Label '{label.name}' has been removed from the selected label set.")
		if isinstance(label_id, str):
			raise ValueError(f"Label {label_id} is missing from the selected label set.")
		raise ValueError("An object is unassigned and has no export class.")

	def validateItems(self, items) -> None:
		items = list(items)
		unassigned_count = sum(getattr(item, "label_id", None) is None for item in items)
		if unassigned_count and not self._allow_unassigned:
			raise UnassignedObjectsError(unassigned_count)
		for item in items:
			self.classIdForItem(item)

	@contextmanager
	def allowingUnassigned(self):
		previous_value = self._allow_unassigned
		self._allow_unassigned = True
		try:
			yield
		finally:
			self._allow_unassigned = previous_value

	def projectItems(self):
		from ..activity.object_detection_activity import BoxItem, ObjectDetectionActivity
		from ..activity.object_segmentation_activity import ObjectSegmentationActivity, PathItem

		activities = self.app()._activities
		return [
			item
			for activity, item_type in (
				(activities[ObjectDetectionActivity.IDENTIFIER], BoxItem),
				(activities[ObjectSegmentationActivity.IDENTIFIER], PathItem),
			)
			for item in activity.items()
			if isinstance(item, item_type)
		]

	def annotationTypeDefaults(self) -> tuple[bool, bool]:
		from ..activity.object_detection_activity import BoxItem
		from ..activity.object_segmentation_activity import PathItem

		items = self.projectItems()
		return (
			any(isinstance(item, BoxItem) for item in items),
			any(isinstance(item, PathItem) for item in items),
		)

	def trackIds(self) -> dict[int, int]:
		"""Return stable project-wide track IDs in first-appearance order."""
		from ..activity.object_detection_activity import BoxItem
		from ..activity.object_segmentation_activity import PathItem

		items = self.projectItems()
		track_ids: dict[int, int] = {}

		for item_type in (BoxItem, PathItem):
			for frame_index in range(len(self.app().mediaManager().imagePaths())):
				for item in items:
					if isinstance(item, item_type) and item.isAlive(frame_index):
						track_ids.setdefault(id(item), len(track_ids))

		# Metadata is object-level, so include objects with no alive frame too.
		for item in items:
			track_ids.setdefault(id(item), len(track_ids))

		return track_ids

	def _objectProperties(self, item) -> dict:
		label_set = self.app().labelSet()
		label = label_set.active_label(item.label_id) if label_set is not None else None
		if label is None:
			return {}
		return {
			metadata_field.name: item.metadata[metadata_field.id]
			for metadata_field in label.fields
			if metadata_field.id in item.metadata
		}

	def exportMetadata(self, path: Path, track_ids: Optional[dict[int, int]] = None) -> None:
		items = self.projectItems()
		self.validateItems(items)
		if track_ids is None:
			track_ids = self.trackIds()
		data = {
			"objects": {
				str(track_ids[id(item)]): {
					"class_id": self.classIdForItem(item),
					"object_properties": self._objectProperties(item),
				}
				for item in sorted(items, key=lambda value: track_ids[id(value)])
			}
		}
		path.mkdir(parents=True, exist_ok=True)
		with (path / "metadata.json").open("w", encoding="utf-8") as file:
			json.dump(data, file, indent=2)
			file.write("\n")

	def show(self, parent: Optional[QWidget] = None) -> None:
		raise NotImplementedError
