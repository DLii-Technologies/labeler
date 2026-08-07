from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING
from PyQt6.QtWidgets import QWidget

if TYPE_CHECKING:
	from ..application import Application

class Exporter:

	def __init__(self):
		pass

	def app(self) -> "Application":
		from ..application import Application
		return Application.instance()

	def export(self, options: Any) -> None:
		raise NotImplementedError

	def classIdForItem(self, item) -> int:
		label_set = self.app().labelSet()
		if label_set is None:
			raise ValueError("No label set is selected for this project.")
		label_id = getattr(item, "label_id", None)
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
		for item in items:
			self.classIdForItem(item)

	def show(self, parent: Optional[QWidget] = None) -> None:
		raise NotImplementedError
