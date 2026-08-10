from pathlib import Path
from typing import Dict, Optional, Union
from PyQt6.QtCore import (
	QEvent,
	QStandardPaths,
	QTimer,
	Qt,
	pyqtSignal
)
from PyQt6.QtGui import (
	QImage,
	QPixmap
)
from PyQt6.QtWidgets import (
	QApplication,
	QAbstractItemView,
	QComboBox,
	QFileDialog,
	QLineEdit,
	QMessageBox,
	QWidget
)

try:
	from .gen.manifest import MANIFEST
except ModuleNotFoundError:
	# The build script generates this module. Keep source checkouts usable before
	# the first build as well.
	MANIFEST = {
		"name": "dlii-labeler",
		"display_name": "Labeler",
		"version": "0.0.0",
		"organization": "DLii Technologies",
		"organization_domain": "dlii.tech",
	}
from .activity import Activity
from .activity.object_detection_activity import ObjectDetectionActivity
from .activity.object_segmentation_activity import ObjectSegmentationActivity
from .data_store import DataStore
from .export.tngo_exporter import TngoExporter
from .export.yolo_exporter import YoloExporter
from .media_manager import MediaManager
from .label_sets import (
	DEFAULT_LABEL_COLORS,
	LabelSet,
	LabelSetCatalog,
	collect_annotation_label_references,
)

class Application(QApplication):

	folderOpened = pyqtSignal(str)
	imageChanged = pyqtSignal(QPixmap)
	labelSetChanged = pyqtSignal()
	labelCatalogChanged = pyqtSignal()

	@classmethod
	def instance(cls) -> "Application":
		return QApplication.instance() # type: ignore

	def __init__(self, argv):
		super().__init__(argv)

		self._data_store: Optional[DataStore] = None
		self._folder_path: Optional[Path] = None

		self.setApplicationName(MANIFEST["display_name"])
		self.setApplicationVersion(MANIFEST["version"])
		self.setOrganizationName(MANIFEST["organization"])
		self.setOrganizationDomain(MANIFEST["organization_domain"])

		app_data_path = Path(
			QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
		)
		self._label_catalog = LabelSetCatalog(app_data_path / "label_sets.json")
		self._label_set: Optional[LabelSet] = None

		self._media_manager = MediaManager()
		self._media_manager.frameIndexChanged.connect(self._saveCurrentFrame)

		self._activities = {
			Activity.IDENTIFIER: Activity(),
			ObjectDetectionActivity.IDENTIFIER: ObjectDetectionActivity(),
			ObjectSegmentationActivity.IDENTIFIER: ObjectSegmentationActivity()
		}
		for activity in self._activities.values():
			self.imageChanged.connect(activity.setPixmap)
			activity.changed.connect(self._pruneLabelTombstones)

		self._exporters = {
		    TngoExporter.IDENTIFIER: TngoExporter(),
			YoloExporter.IDENTIFIER: YoloExporter()
		}

		w, h = 1280, 720
		image = QImage(w, h, QImage.Format.Format_RGB32)
		for y in range(h):
			line = (y * 255) // max(1, h - 1)
			for x in range(w):
				r = (x * 255) // max(1, w - 1)
				image.setPixel(x, y, (255 << 24) | (r << 16) | (line << 8) | 32)
		self.setPixmap(QPixmap.fromImage(image))

	def notify(self, receiver, event) -> bool:
		if event.type() == QEvent.Type.KeyPress and isinstance(receiver, QLineEdit):
			if (
				event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
				and not self._isItemViewEditor(receiver)
			):
				QTimer.singleShot(0, receiver.clearFocus)
		elif event.type() == QEvent.Type.MouseButtonPress:
			focused_widget = self.focusWidget()
			if (
				isinstance(focused_widget, QLineEdit)
				and not self._isItemViewEditor(focused_widget)
				and receiver is not focused_widget
				and not self._isEditorRelatedWidget(focused_widget, receiver)
			):
				focused_widget.clearFocus()
		return super().notify(receiver, event)

	def _isItemViewEditor(self, editor: QLineEdit) -> bool:
		parent = editor.parentWidget()
		while parent is not None:
			if isinstance(parent, QAbstractItemView):
				return True
			parent = parent.parentWidget()
		return False

	def _isEditorRelatedWidget(self, editor: QLineEdit, receiver) -> bool:
		"""Keep editable combo-box popups from committing the editor too early."""
		parent = editor.parentWidget()
		while parent is not None:
			if isinstance(parent, QComboBox):
				return parent is receiver or parent.isAncestorOf(receiver)
			parent = parent.parentWidget()
		return False

	def activities(self) -> Dict[str, Activity]:
		return self._activities

	def dataStore(self) -> Optional[DataStore]:
		return self._data_store

	def labelCatalog(self) -> LabelSetCatalog:
		return self._label_catalog

	def labelSet(self) -> Optional[LabelSet]:
		return self._label_set

	def projectLabelIds(self) -> set[str]:
		return {
			item.label_id
			for activity in self._activities.values()
			for item in activity.items()
			if isinstance(getattr(item, "label_id", None), str)
		}

	def _serializedProjectLabelReferences(self) -> tuple[list[str], set[str]]:
		legacy_names: list[str] = []
		legacy_seen: set[str] = set()
		label_ids: set[str] = set()
		if self._data_store is None:
			return legacy_names, label_ids

		for activity in self._activities.values():
			raw_data = self._data_store.get(activity.IDENTIFIER)
			names, ids = collect_annotation_label_references(raw_data)
			for name in names:
				if name not in legacy_seen:
					legacy_seen.add(name)
					legacy_names.append(name)
			label_ids.update(ids)
		return legacy_names, label_ids

	def _prepareProjectLabelSet(self) -> None:
		if self._data_store is None:
			self._label_set = None
			return

		legacy_names, referenced_ids = self._serializedProjectLabelReferences()
		local_data = self._data_store.get("label_set")
		local_set = LabelSet.from_dict(local_data)
		selected_id = self._data_store.get("label_set_id")

		if local_set is None and isinstance(selected_id, str):
			local_set = self._label_catalog.get(selected_id)

		if local_set is None and legacy_names:
			local_set = LabelSet.create(f"{self._folder_path.name} Labels")
			for index, name in enumerate(legacy_names):
				local_set.add_label(name, DEFAULT_LABEL_COLORS[index % len(DEFAULT_LABEL_COLORS)])

		if local_set is not None:
			catalog_set = self._label_catalog.merge_local(local_set)
			local_set = local_set.synchronize(catalog_set, referenced_ids)
			self._data_store.set("label_set", local_set.to_dict())
			self._data_store.set("label_set_id", local_set.id)

		self._label_set = local_set

	def setLabelSet(self, set_id: str) -> bool:
		label_set = self._label_catalog.get(set_id)
		if label_set is None:
			return False
		self._label_set = label_set
		if self._data_store is not None:
			self._data_store.set("label_set", label_set.to_dict())
			self._data_store.set("label_set_id", label_set.id)
		self.labelSetChanged.emit()
		return True

	def clearLabelSet(self) -> None:
		self._label_set = None
		if self._data_store is not None:
			self._data_store.set("label_set", None)
			self._data_store.set("label_set_id", None)
		self.labelSetChanged.emit()

	def syncLabelSet(self) -> None:
		if self._label_set is None:
			return
		catalog_set = self._label_catalog.get(self._label_set.id)
		if catalog_set is not None:
			self._label_set = self._label_set.synchronize(catalog_set, self.projectLabelIds())
		if self._data_store is not None:
			self._data_store.set("label_set", self._label_set.to_dict())
			self._data_store.set("label_set_id", self._label_set.id)
		self.labelSetChanged.emit()

	def notifyLabelCatalogChanged(self) -> None:
		self.syncLabelSet()
		self.labelCatalogChanged.emit()

	def _pruneLabelTombstones(self, *_args) -> None:
		if self._label_set is None or not self._label_set.tombstones:
			return
		referenced_ids = self.projectLabelIds()
		remaining = {
			label_id: label
			for label_id, label in self._label_set.tombstones.items()
			if label_id in referenced_ids
		}
		if len(remaining) == len(self._label_set.tombstones):
			return
		self._label_set.tombstones = remaining
		if self._data_store is not None:
			self._data_store.set("label_set", self._label_set.to_dict())

	def mediaManager(self) -> MediaManager:
		return self._media_manager

	def folderPath(self) -> Path:
		return self._folder_path

	def setPixmap(self, image: QPixmap):
		self.imageChanged.emit(image)

	def _saveCurrentFrame(self, frame_index: int) -> None:
		data_store = self._data_store
		if data_store is None:
			return
		data_store.set("last_frame", frame_index)

	def openFolder(self, folder_path: Optional[Union[Path, str]] = None, parent: Optional[QWidget] = None) -> bool:
		if not folder_path is not None:
			# Open a file dialog to select a folder of images
			current_directory = str(self._media_manager.folder() or "") or None
			folder_path = QFileDialog.getExistingDirectory(parent, "Open Folder", directory=current_directory)
			if not folder_path:
				return False
		self._folder_path = Path(folder_path)
		if self._data_store is not None:
			self._data_store.close()
		self._data_store = DataStore(folder_path)
		self._prepareProjectLabelSet()
		last_frame = self._data_store.get("last_frame")
		self._media_manager.setFolder(folder_path)
		if isinstance(last_frame, int) and self._media_manager.length() > 0:
			last_frame = min(max(last_frame, 0), self._media_manager.length() - 1)
			self._media_manager.setIndex(last_frame)
		self.folderOpened.emit(folder_path)
		if not self._data_store.checkVersion():
			# Alert the user the data may be incompatible. Ask to continue
			if QMessageBox.warning(
				parent,
				"Warning",
				"Data store version mismatch. Data may be incompatible. Continue?",
				QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
			) == QMessageBox.StandardButton.No:
				self.exit()
				return False
		return True
