from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPixmap
from PyQt6.QtWidgets import (
	QColorDialog,
	QComboBox,
	QDialog,
	QHBoxLayout,
	QInputDialog,
	QLabel,
	QLineEdit,
	QListWidget,
	QListWidgetItem,
	QMessageBox,
	QPushButton,
	QSizePolicy,
	QSpinBox,
	QVBoxLayout,
)

from ..label_sets import LabelSet, MetadataFieldType


class LabelSetManagerDialog(QDialog):
	"""Edit the application-wide label-set catalog."""

	def __init__(self, parent=None):
		super().__init__(parent)
		from ..application import Application
		self._app = Application.instance()
		self._working_set: Optional[LabelSet] = None
		self._loading = False

		self.setWindowTitle("Label Set Manager")
		self.resize(720, 460)

		self._sets = QListWidget()
		self._sets.currentItemChanged.connect(self._setSelected)

		new_set = QPushButton("New Set")
		new_set.clicked.connect(self._newSet)
		delete_set = QPushButton("Delete Set")
		delete_set.clicked.connect(self._deleteSet)
		left_layout = QVBoxLayout()
		left_layout.addWidget(QLabel("Label Sets"))
		left_layout.addWidget(self._sets)

		self._name = QLineEdit()
		self._name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
		self._name.editingFinished.connect(self._saveName)

		self._labels = QListWidget()
		self._labels.setDragDropMode(QListWidget.DragDropMode.InternalMove)
		self._labels.setDefaultDropAction(Qt.DropAction.MoveAction)
		self._labels.setEditTriggers(
			QListWidget.EditTrigger.DoubleClicked | QListWidget.EditTrigger.EditKeyPressed
		)
		self._labels.currentItemChanged.connect(self._labelSelected)
		self._labels.itemChanged.connect(self._labelChanged)
		self._labels.model().rowsMoved.connect(self._labelsReordered)

		self._fields = QListWidget()
		self._fields.setDragDropMode(QListWidget.DragDropMode.InternalMove)
		self._fields.setDefaultDropAction(Qt.DropAction.MoveAction)
		self._fields.setEditTriggers(
			QListWidget.EditTrigger.DoubleClicked | QListWidget.EditTrigger.EditKeyPressed
		)
		self._fields.currentItemChanged.connect(self._fieldSelected)
		self._fields.itemChanged.connect(self._fieldChanged)
		self._fields.model().rowsMoved.connect(self._fieldsReordered)

		self._field_type = QComboBox()
		for field_type in MetadataFieldType:
			self._field_type.addItem(field_type.display_name, int(field_type))
		self._field_type.currentIndexChanged.connect(self._fieldTypeChanged)

		self._decimal_places = QSpinBox()
		self._decimal_places.setRange(0, 10)
		self._decimal_places.valueChanged.connect(self._decimalPlacesChanged)

		add_label = QPushButton("Add")
		add_label.clicked.connect(self._addLabel)
		remove_label = QPushButton("Remove")
		remove_label.clicked.connect(self._removeLabel)
		color_label = QPushButton("Color...")
		color_label.clicked.connect(self._changeColor)
		label_buttons = QHBoxLayout()
		label_buttons.addWidget(add_label)
		label_buttons.addWidget(remove_label)
		label_buttons.addWidget(color_label)
		label_buttons.addStretch()

		add_field = QPushButton("Add")
		add_field.clicked.connect(self._addField)
		remove_field = QPushButton("Remove")
		remove_field.clicked.connect(self._removeField)
		field_buttons = QHBoxLayout()
		field_buttons.addWidget(add_field)
		field_buttons.addWidget(remove_field)
		field_buttons.addWidget(QLabel("Type:"))
		field_buttons.addWidget(self._field_type)
		field_buttons.addWidget(QLabel("Decimal places:"))
		field_buttons.addWidget(self._decimal_places)
		field_buttons.addStretch()

		right_layout = QVBoxLayout()
		right_layout.addWidget(QLabel("Name"))
		right_layout.addWidget(self._name)
		right_layout.addWidget(QLabel("Labels"))
		right_layout.addWidget(self._labels, 1)
		right_layout.addLayout(label_buttons)
		right_layout.addWidget(QLabel("Fields"))
		right_layout.addWidget(self._fields, 1)
		right_layout.addLayout(field_buttons)

		content = QHBoxLayout()
		content.addLayout(left_layout, 1)
		content.addLayout(right_layout, 2)

		bottom_buttons = QHBoxLayout()
		bottom_buttons.addWidget(new_set)
		bottom_buttons.addWidget(delete_set)
		bottom_buttons.addStretch()
		close_button = QPushButton("Close")
		close_button.clicked.connect(self.reject)
		bottom_buttons.addWidget(close_button)

		layout = QVBoxLayout(self)
		layout.addLayout(content, 1)
		layout.addLayout(bottom_buttons)

		# Refresh after QListWidget delegate editors finish committing. Rebuilding a
		# list synchronously from itemChanged can destroy the active editor before
		# QAbstractItemView has finished handling its commitData signal.
		self._app.labelCatalogChanged.connect(
			self._refreshSets,
			Qt.ConnectionType.QueuedConnection,
		)
		self._refreshSets()

	def _refreshSets(self) -> None:
		selected_id = self._working_set.id if self._working_set is not None else None
		self._loading = True
		try:
			self._sets.clear()
			for label_set in sorted(self._app.labelCatalog().all(), key=lambda value: value.name.lower()):
				item = QListWidgetItem(label_set.name)
				item.setData(Qt.ItemDataRole.UserRole, label_set.id)
				self._sets.addItem(item)
			if selected_id is not None:
				for index in range(self._sets.count()):
					if self._sets.item(index).data(Qt.ItemDataRole.UserRole) == selected_id:
						self._sets.setCurrentRow(index)
						break
			if self._sets.currentItem() is None and self._sets.count() > 0:
				self._sets.setCurrentRow(0)
		finally:
			self._loading = False
		if self._working_set is None and self._sets.currentItem() is not None:
			self._setSelected(self._sets.currentItem(), None)

	def _setSelected(self, current: Optional[QListWidgetItem], _previous) -> None:
		if self._loading:
			return
		if current is None:
			self._working_set = None
			self._showWorkingSet()
			return
		set_id = current.data(Qt.ItemDataRole.UserRole)
		self._working_set = self._app.labelCatalog().get(set_id)
		self._showWorkingSet()

	def _showWorkingSet(self) -> None:
		self._loading = True
		try:
			self._name.setEnabled(self._working_set is not None)
			self._labels.setEnabled(self._working_set is not None)
			self._fields.setEnabled(self._working_set is not None)
			self._name.setText(self._working_set.name if self._working_set is not None else "")
			self._labels.clear()
			if self._working_set is not None:
				for label in self._working_set.labels:
					item = QListWidgetItem(label.name)
					item.setData(Qt.ItemDataRole.UserRole, label.id)
					item.setIcon(self._colorIcon(label.color))
					item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
					self._labels.addItem(item)
			if self._labels.count() > 0:
				self._labels.setCurrentRow(0)
		finally:
			self._loading = False
		self._labelSelected(self._labels.currentItem(), None)

	def _selectedLabel(self):
		if self._working_set is None or self._labels.currentItem() is None:
			return None
		label_id = self._labels.currentItem().data(Qt.ItemDataRole.UserRole)
		return next((label for label in self._working_set.labels if label.id == label_id), None)

	def _labelSelected(self, _current: Optional[QListWidgetItem], _previous) -> None:
		label = self._selectedLabel()
		self._loading = True
		try:
			self._fields.clear()
			self._field_type.setEnabled(label is not None)
			self._decimal_places.setEnabled(False)
			if label is not None:
				for metadata_field in label.fields:
					item = QListWidgetItem(metadata_field.name)
					item.setData(Qt.ItemDataRole.UserRole, metadata_field.id)
					item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
					self._fields.addItem(item)
		finally:
			self._loading = False
		self._fieldSelected(self._fields.currentItem(), None)

	def _selectedField(self):
		label = self._selectedLabel()
		if label is None or self._fields.currentItem() is None:
			return None
		field_id = self._fields.currentItem().data(Qt.ItemDataRole.UserRole)
		return label.field(field_id)

	def _fieldSelected(self, _current: Optional[QListWidgetItem], _previous) -> None:
		metadata_field = self._selectedField()
		self._loading = True
		try:
			self._field_type.setEnabled(metadata_field is not None)
			self._decimal_places.setEnabled(
				metadata_field is not None and metadata_field.type == MetadataFieldType.DECIMAL
			)
			if metadata_field is not None:
				self._field_type.setCurrentIndex(self._field_type.findData(int(metadata_field.type)))
				self._decimal_places.setValue(metadata_field.decimal_places)
		finally:
			self._loading = False

	def _colorIcon(self, color: str) -> QIcon:
		pixmap = QPixmap(18, 18)
		pixmap.fill(QColor(color))
		return QIcon(pixmap)

	def _saveWorkingSet(self) -> None:
		if self._working_set is None:
			return
		name = self._name.text().strip()
		if not name:
			QMessageBox.warning(self, "Invalid Name", "A label set must have a name.")
			self._showWorkingSet()
			return
		self._working_set.name = name
		self._working_set = self._app.labelCatalog().save(self._working_set)
		self._app.notifyLabelCatalogChanged()

	def _saveName(self) -> None:
		if not self._loading:
			self._saveWorkingSet()

	def _labelChanged(self, item: QListWidgetItem) -> None:
		if self._loading or self._working_set is None:
			return
		name = item.text().strip()
		duplicate = any(
			label.name == name and label.id != item.data(Qt.ItemDataRole.UserRole)
			for label in self._working_set.labels
		)
		if not name or duplicate:
			QMessageBox.warning(self, "Invalid Label", "Labels must have unique, non-empty names.")
			self._showWorkingSet()
			return
		for label in self._working_set.labels:
			if label.id == item.data(Qt.ItemDataRole.UserRole):
				label.name = name
				break
		self._saveWorkingSet()

	def _labelsReordered(self, *_args) -> None:
		if self._loading or self._working_set is None:
			return
		by_id = {label.id: label for label in self._working_set.labels}
		self._working_set.labels = [
			by_id[self._labels.item(index).data(Qt.ItemDataRole.UserRole)]
			for index in range(self._labels.count())
		]
		self._saveWorkingSet()

	def _fieldChanged(self, item: QListWidgetItem) -> None:
		if self._loading:
			return
		label = self._selectedLabel()
		if label is None:
			return
		name = item.text().strip()
		duplicate = any(
			metadata_field.name == name
			and metadata_field.id != item.data(Qt.ItemDataRole.UserRole)
			for metadata_field in label.fields
		)
		if not name or duplicate:
			QMessageBox.warning(self, "Invalid Field", "Fields must have unique, non-empty names.")
			self._labelSelected(self._labels.currentItem(), None)
			return
		metadata_field = label.field(item.data(Qt.ItemDataRole.UserRole))
		if metadata_field is not None:
			metadata_field.name = name
		self._saveWorkingSet()

	def _fieldsReordered(self, *_args) -> None:
		if self._loading:
			return
		label = self._selectedLabel()
		if label is None:
			return
		by_id = {metadata_field.id: metadata_field for metadata_field in label.fields}
		label.fields = [
			by_id[self._fields.item(index).data(Qt.ItemDataRole.UserRole)]
			for index in range(self._fields.count())
		]
		self._saveWorkingSet()

	def _fieldTypeChanged(self, _index: int) -> None:
		if self._loading:
			return
		metadata_field = self._selectedField()
		if metadata_field is None:
			return
		metadata_field.type = MetadataFieldType(int(self._field_type.currentData()))
		self._saveWorkingSet()
		self._fieldSelected(self._fields.currentItem(), None)

	def _decimalPlacesChanged(self, value: int) -> None:
		if self._loading:
			return
		metadata_field = self._selectedField()
		if metadata_field is None or metadata_field.type != MetadataFieldType.DECIMAL:
			return
		metadata_field.decimal_places = value
		self._saveWorkingSet()

	def _addField(self) -> None:
		label = self._selectedLabel()
		if label is None:
			return
		base_name = "New Field"
		name = base_name
		index = 2
		while any(metadata_field.name == name for metadata_field in label.fields):
			name = f"{base_name} {index}"
			index += 1
		metadata_field = label.add_field(name, MetadataFieldType.STRING)
		self._saveWorkingSet()
		self._labelSelected(self._labels.currentItem(), None)
		for index in range(self._fields.count()):
			if self._fields.item(index).data(Qt.ItemDataRole.UserRole) == metadata_field.id:
				self._fields.setCurrentRow(index)
				self._fields.editItem(self._fields.item(index))
				break

	def _removeField(self) -> None:
		label = self._selectedLabel()
		metadata_field = self._selectedField()
		if label is None or metadata_field is None:
			return
		answer = QMessageBox.question(
			self,
			"Remove Field",
			f"Remove '{metadata_field.name}' from label '{label.name}'? Existing values will be hidden.",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return
		label.remove_field(metadata_field.id)
		self._saveWorkingSet()
		self._labelSelected(self._labels.currentItem(), None)

	def _newSet(self) -> None:
		name, accepted = QInputDialog.getText(self, "New Label Set", "Name:")
		if not accepted or not name.strip():
			return
		label_set = self._app.labelCatalog().create(name.strip())
		self._app.notifyLabelCatalogChanged()
		self._working_set = label_set
		self._refreshSets()

	def _deleteSet(self) -> None:
		if self._working_set is None:
			return
		answer = QMessageBox.question(
			self,
			"Delete Label Set",
			f"Delete '{self._working_set.name}' from the global catalog? Existing projects keep local copies.",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return
		self._app.labelCatalog().delete(self._working_set.id)
		self._working_set = None
		self._app.notifyLabelCatalogChanged()
		self._refreshSets()

	def _addLabel(self) -> None:
		if self._working_set is None:
			return
		base_name = "New Label"
		name = base_name
		index = 2
		while any(label.name == name for label in self._working_set.labels):
			name = f"{base_name} {index}"
			index += 1
		label = self._working_set.add_label(name)
		self._saveWorkingSet()
		self._showWorkingSet()
		for index in range(self._labels.count()):
			if self._labels.item(index).data(Qt.ItemDataRole.UserRole) == label.id:
				self._labels.setCurrentRow(index)
				self._labels.editItem(self._labels.item(index))
				break

	def _removeLabel(self) -> None:
		if self._working_set is None:
			return
		item = self._labels.currentItem()
		if item is None:
			return
		answer = QMessageBox.question(
			self,
			"Remove Label",
			f"Remove '{item.text()}' from this label set? Referencing projects will retain tombstones.",
			QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
		)
		if answer != QMessageBox.StandardButton.Yes:
			return
		self._working_set.remove_label(item.data(Qt.ItemDataRole.UserRole))
		self._saveWorkingSet()
		self._showWorkingSet()

	def _changeColor(self) -> None:
		if self._working_set is None:
			return
		item = self._labels.currentItem()
		if item is None:
			return
		label = next(
			(label for label in self._working_set.labels if label.id == item.data(Qt.ItemDataRole.UserRole)),
			None,
		)
		if label is None:
			return
		color = QColorDialog.getColor(QColor(label.color), self, "Select Label Color")
		if not color.isValid():
			return
		label.color = color.name(QColor.NameFormat.HexRgb)
		self._saveWorkingSet()
		self._showWorkingSet()
