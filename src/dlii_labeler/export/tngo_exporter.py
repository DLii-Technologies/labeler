from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import (
	QDialog,
	QCheckBox,
	QDialogButtonBox,
	QFileDialog,
	QHBoxLayout,
	QLineEdit,
	QPushButton,
	QVBoxLayout,
	QWidget,
)

from ..activity.object_detection_activity import BoxItem
from . import Exporter


class TngoExporter(Exporter):

	IDENTIFIER = "TNGO"

	@dataclass
	class Options:
		object_detection: bool = True
		object_segmentation: bool = False
		include_empty_frames: bool = False

	def _track_id_for_item(self, item, track_ids: dict[int, int]) -> int:
		item_key = id(item)

		if item_key not in track_ids:
			track_ids[item_key] = len(track_ids)

		return track_ids[item_key]

	def _export_object_detection(
		self,
		path: Path,
		options: Options,
		track_ids: dict[int, int],
	) -> None:
		from ..activity.object_detection_activity import ObjectDetectionActivity

		activity = self.app()._activities[ObjectDetectionActivity.IDENTIFIER]

		for frame_index, image_path in enumerate(self.app().mediaManager().imagePaths()):
			lines = []

			for item in activity.items():
				if not isinstance(item, BoxItem):
					continue

				if not item.isAlive(frame_index):
					continue

				track_id = self._track_id_for_item(item, track_ids)

				state = item.stateForFrame(frame_index)
				center_uv = QRectF(state.u, state.v, state.width, state.height).center()

				class_id = 0
				lines.append(
					f"{track_id} {class_id} "
					f"{center_uv.x()} {center_uv.y()} {state.width} {state.height}"
				)

			if not lines and not options.include_empty_frames:
				continue

			with open(path / f"{image_path.stem}.txt", "w") as f:
				f.write("\n".join(lines))

	def _export_object_segmentation(
		self,
		path: Path,
		options: Options,
		track_ids: dict[int, int],
	) -> None:
		from ..activity.object_segmentation_activity import (
			ObjectSegmentationActivity,
			PathItem,
		)

		activity = self.app()._activities[ObjectSegmentationActivity.IDENTIFIER]

		for frame_index, image_path in enumerate(self.app().mediaManager().imagePaths()):
			lines = []

			for item in activity.items():
				if not isinstance(item, PathItem):
					continue

				if not item.isAlive(frame_index):
					continue

				track_id = self._track_id_for_item(item, track_ids)

				state = item.stateForFrame(frame_index)
				points = [QPointF(state.u + x, state.v + y) for x, y in state.points]

				class_id = 0
				line = f"{track_id} {class_id} {' '.join(f'{p.x()} {p.y()}' for p in points)}"
				lines.append(line)

			if not lines and not options.include_empty_frames:
				continue

			with open(path / f"{image_path.stem}.txt", "w") as f:
				f.write("\n".join(lines))

	def export(self, path: Path, options: Options) -> None:
		path.mkdir(parents=True, exist_ok=True)

		track_ids: dict[int, int] = {}

		if options.object_detection:
			self._export_object_detection(path, options, track_ids)

		if options.object_segmentation:
			self._export_object_segmentation(path, options, track_ids)

	def show(self, parent: Optional[QWidget] = None) -> None:
		dialog = QDialog(parent)
		dialog.setWindowTitle("TNGO Export Options")

		layout = QVBoxLayout()

		folder_layout = QHBoxLayout()

		self._folder_path_edit = QLineEdit()
		self._folder_path_edit.setPlaceholderText("Select export folder...")
		self._folder_path_edit.setReadOnly(True)
		self._folder_path_edit.setText(str(self.app().folderPath()))
		folder_layout.addWidget(self._folder_path_edit)

		browse_button = QPushButton("Browse...")

		def select_folder():
			folder = QFileDialog.getExistingDirectory(
				dialog,
				"Select Export Folder",
				self._folder_path_edit.text(),
			)
			if folder:
				self._folder_path_edit.setText(folder)

		browse_button.clicked.connect(select_folder)
		folder_layout.addWidget(browse_button)

		layout.addLayout(folder_layout)

		object_detection_checkbox = QCheckBox("Object Detection")
		object_detection_checkbox.setChecked(True)
		layout.addWidget(object_detection_checkbox)

		object_segmentation_checkbox = QCheckBox("Object Segmentation")
		object_segmentation_checkbox.setChecked(False)
		layout.addWidget(object_segmentation_checkbox)

		include_empty_checkbox = QCheckBox("Include empty frames")
		include_empty_checkbox.setChecked(False)
		layout.addWidget(include_empty_checkbox)

		button_box = QDialogButtonBox(
			QDialogButtonBox.StandardButton.Ok
			| QDialogButtonBox.StandardButton.Cancel
		)
		button_box.accepted.connect(dialog.accept)
		button_box.rejected.connect(dialog.reject)
		layout.addWidget(button_box)

		dialog.setLayout(layout)
		dialog.setMinimumWidth(400)

		if dialog.exec() != QDialog.DialogCode.Accepted:
			return

		options = self.Options(
			object_detection=object_detection_checkbox.isChecked(),
			object_segmentation=object_segmentation_checkbox.isChecked(),
			include_empty_frames=include_empty_checkbox.isChecked(),
		)

		self.export(Path(self._folder_path_edit.text()), options)
