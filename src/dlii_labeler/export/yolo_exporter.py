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
	QWidget
)

from ..activity.object_detection_activity import BoxItem
from . import Exporter

class YoloExporter(Exporter):

	IDENTIFIER = "YOLO"

	@dataclass
	class Options:
		object_detection: bool = True
		object_segmentation: bool = False
		include_empty_frames: bool = False

	def _export_object_detection(self, path: Path, options: Options) -> None:
		from ..activity.object_detection_activity import ObjectDetectionActivity
		activity = self.app()._activities[ObjectDetectionActivity.IDENTIFIER]
		for frame_index, image_path in enumerate(self.app().mediaManager().imagePaths()):
			lines = []
			for item in activity.items():
				if not isinstance(item, BoxItem):
					continue
				if not item.isAlive(frame_index):
					continue
				state = item.stateForFrame(frame_index)
				center_uv = QRectF(state.u, state.v, state.width, state.height).center()
				lines.append(f"0 {center_uv.x()} {center_uv.y()} {state.width} {state.height}")
			if not lines and not options.include_empty_frames:
				continue
			with open(path / f"{image_path.stem}.txt", "w") as f:
				f.write("\n".join(lines))

	def _export_object_segmentation(self, path: Path, options: Options) -> None:
		from ..activity.object_segmentation_activity import ObjectSegmentationActivity, PathItem
		activity = self.app()._activities[ObjectSegmentationActivity.IDENTIFIER]
		for frame_index, image_path in enumerate(self.app().mediaManager().imagePaths()):
			lines = []
			for item in activity.items():
				if not isinstance(item, PathItem):
					continue
				if not item.isAlive(frame_index):
					continue
				state = item.stateForFrame(frame_index)
				points = [QPointF(state.u + x, state.v + y) for x, y in state.points]
				line = f"0 {' '.join(f'{p.x()} {p.y()}' for p in points)}"
				lines.append(line)
			if not lines and not options.include_empty_frames:
				continue
			with open(path / f"{image_path.stem}.txt", "w") as f:
				f.write("\n".join(lines))


	def export(self, path: Path, options: Options) -> None:
		if options.object_detection:
			self._export_object_detection(path, options)
		if options.object_segmentation:
			self._export_object_segmentation(path, options)

	def show(self, parent: Optional[QWidget] = None) -> None:
		# Show a modal dialog with options
		dialog = QDialog(parent)
		dialog.setWindowTitle("YOLO Export Options")

		layout = QVBoxLayout()

		# Add folder selection
		folder_layout = QHBoxLayout()
		self._folder_path_edit = QLineEdit()
		self._folder_path_edit.setPlaceholderText("Select export folder...")
		self._folder_path_edit.setReadOnly(True)
		self._folder_path_edit.setText(str(self.app().folderPath()))
		folder_layout.addWidget(self._folder_path_edit)

		browse_button = QPushButton("Browse...")
		def select_folder():
			folder = QFileDialog.getExistingDirectory(dialog, "Select Export Folder", self._folder_path_edit.text())
			if folder:
				self._folder_path_edit.setText(folder)
		browse_button.clicked.connect(select_folder)
		folder_layout.addWidget(browse_button)
		layout.addLayout(folder_layout)

		# Add option checkboxes
		object_detection_checkbox = QCheckBox("Object Detection")
		object_detection_checkbox.setChecked(True)
		layout.addWidget(object_detection_checkbox)

		object_segmentation_checkbox = QCheckBox("Object Segmentation")
		object_segmentation_checkbox.setChecked(False)
		layout.addWidget(object_segmentation_checkbox)

		# Add option checkboxes
		include_empty_checkbox = QCheckBox("Include empty frames")
		include_empty_checkbox.setChecked(False)
		layout.addWidget(include_empty_checkbox)

		# Add OK/Cancel buttons
		button_box = QDialogButtonBox(
			QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
		)
		button_box.accepted.connect(dialog.accept)
		button_box.rejected.connect(dialog.reject)
		layout.addWidget(button_box)

		dialog.setLayout(layout)
		dialog.setMinimumWidth(400)

		if dialog.exec() != QDialog.DialogCode.Accepted:
			return

		options = self.Options(
			object_detection_checkbox.isChecked(),
			object_segmentation_checkbox.isChecked(),
			include_empty_checkbox.isChecked()
		)

		self.export(Path(self._folder_path_edit.text()), options)
