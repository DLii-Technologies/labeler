from typing import Optional

from PyQt6.QtCore import QSignalBlocker, QTimer
from PyQt6.QtGui import QDoubleValidator, QIntValidator
from PyQt6.QtWidgets import (
	QComboBox,
	QDoubleSpinBox,
	QFormLayout,
	QGroupBox,
	QLabel,
	QLineEdit,
	QMessageBox,
	QSizePolicy,
	QVBoxLayout,
	QWidget
)

from ..activity import Activity
from ..label_sets import MetadataField, MetadataFieldType


class ObjectPropertiesWidget(QWidget):
	def __init__(self, parent: Optional[QWidget] = None) -> None:
		super().__init__(parent)

		self._activity: Optional[Activity] = None
		self._items = []
		self._values = {"x": 0.0, "y": 0.0}
		self._metadata_editors: list[tuple[MetadataField, QLineEdit]] = []
		self._refresh_pending = False
		from ..application import Application
		self._app = Application.instance()

		properties = QGroupBox("Object Properties")
		properties_layout = QVBoxLayout()

		self._no_selection = QLabel("No current selection")
		properties_layout.addWidget(self._no_selection)

		self._details = QWidget()
		self._form = QFormLayout()
		self._form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
		self._form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

		self._selection = QLabel("No selection")
		self._form.addRow("Selection", self._selection)

		self._label = QComboBox()
		self._label.setEditable(True)
		self._label.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
		self._label.lineEdit().setPlaceholderText("Multiple values")
		self._label.setSizePolicy(QSizePolicy.Policy.Expanding, self._label.sizePolicy().verticalPolicy())
		self._label.activated.connect(self._selectLabel)
		self._label.lineEdit().editingFinished.connect(self._setLabelFromText)
		self._form.addRow("Label", self._label)

		self._x = self._createPositionSpinBox()
		self._x.setPrefix("X: ")
		self._x.valueChanged.connect(lambda value: self._setPosition("x", value))

		self._y = self._createPositionSpinBox()
		self._y.setPrefix("Y: ")
		self._y.valueChanged.connect(lambda value: self._setPosition("y", value))

		position_inputs = QWidget()
		position_layout = QVBoxLayout(position_inputs)
		position_layout.setContentsMargins(0, 0, 0, 0)
		position_layout.setSpacing(2)
		position_layout.addWidget(self._x)
		position_layout.addWidget(self._y)
		self._form.addRow("Position (X, Y)", position_inputs)

		self._details.setLayout(self._form)
		properties_layout.addWidget(self._details)
		properties.setLayout(properties_layout)
		layout = QVBoxLayout()
		layout.addWidget(properties)
		layout.addStretch()
		self.setLayout(layout)
		self._app.labelSetChanged.connect(self._scheduleRefresh)
		self._app.mediaManager().frameIndexChanged.connect(self._scheduleRefresh)
		self._app.aboutToQuit.connect(self._disconnectActivity)

		self._setEnabled(False)


	def _createPositionSpinBox(self) -> QDoubleSpinBox:
		spin_box = QDoubleSpinBox()
		spin_box.setRange(-1000000.0, 1000000.0)
		spin_box.setDecimals(1)
		spin_box.setSingleStep(1.0)
		spin_box.setSuffix(" px")
		spin_box.setSizePolicy(QSizePolicy.Policy.Expanding, spin_box.sizePolicy().verticalPolicy())
		return spin_box


	def setActivity(self, activity: Activity) -> None:
		self._disconnectActivity()

		self._activity = activity
		self._activity.selectionChanged.connect(self._scheduleRefresh)
		self._activity.geometryChanged.connect(self._scheduleRefresh)
		self._refresh()

	def _disconnectActivity(self) -> None:
		if self._activity is None:
			return
		try:
			self._activity.selectionChanged.disconnect(self._scheduleRefresh)
			self._activity.geometryChanged.disconnect(self._scheduleRefresh)
		except (TypeError, RuntimeError):
			pass
		self._activity = None

	def closeEvent(self, event) -> None:
		self._disconnectActivity()
		try:
			self._app.labelSetChanged.disconnect(self._scheduleRefresh)
			self._app.mediaManager().frameIndexChanged.disconnect(self._scheduleRefresh)
		except (TypeError, RuntimeError):
			pass
		super().closeEvent(event)

	def _setEnabled(self, enabled: bool) -> None:
		self._label.setEnabled(enabled)
		self._x.setEnabled(enabled)
		self._y.setEnabled(enabled)

	def _scheduleRefresh(self, *_args) -> None:
		if self._refresh_pending:
			return
		self._refresh_pending = True
		QTimer.singleShot(0, self._refresh)

	def _refresh(self) -> None:
		self._refresh_pending = False
		self.setUpdatesEnabled(False)
		self._details.setUpdatesEnabled(False)
		try:
			self._refreshContents()
		finally:
			self._details.setUpdatesEnabled(True)
			self.setUpdatesEnabled(True)
			self.update()

	def _refreshContents(self) -> None:
		if self._activity is None:
			self._items = []
		else:
			self._items = [
				item for item in self._activity.selectedItems()
				if hasattr(item, "label_id")
			]

		self._clearMetadataFields()

		if not self._items:
			self._no_selection.show()
			self._details.hide()
			self._setEnabled(False)
			return

		self._no_selection.hide()
		self._details.show()
		self._setEnabled(True)
		count = len(self._items)
		self._selection.setText(f"{count} object" + ("" if count == 1 else "s"))

		label_ids = {item.label_id for item in self._items}
		with QSignalBlocker(self._label):
			self._label.clear()
			self._label.addItem("Unassigned", None)
			label_set = self._app.labelSet()
			if label_set is not None:
				for label in label_set.labels:
					self._label.addItem(label.name, label.id)

				for label_id in sorted(label_ids - label_set.active_label_ids() - {None}):
					label = label_set.label(label_id)
					text = f"Missing: {label.name}" if label is not None else f"Missing: {label_id}"
					self._label.addItem(text, label_id)

			if len(label_ids) == 1:
				label_id = next(iter(label_ids))
				index = self._label.findData(label_id)
				if index >= 0:
					self._label.setCurrentIndex(index)
				else:
					self._label.setEditText(f"Missing: {label_id}")
			else:
				self._label.setCurrentIndex(-1)
				self._label.lineEdit().clear()

		first_item = self._items[0]
		self._values = {"x": first_item.x(), "y": first_item.y()}
		with QSignalBlocker(self._x):
			self._x.setValue(self._values["x"])
		with QSignalBlocker(self._y):
			self._y.setValue(self._values["y"])

		self._addMetadataFields()

	def _clearMetadataFields(self) -> None:
		for _field, editor in self._metadata_editors:
			self._form.removeRow(editor)
		self._metadata_editors.clear()

	def _addMetadataFields(self) -> None:
		label_ids = {item.label_id for item in self._items}
		if len(label_ids) != 1:
			return
		label_set = self._app.labelSet()
		label = label_set.label(next(iter(label_ids))) if label_set is not None else None
		if label is None:
			return

		for metadata_field in label.fields:
			editor = QLineEdit()
			if metadata_field.type == MetadataFieldType.INTEGER:
				editor.setValidator(QIntValidator(-2147483648, 2147483647, editor))
			elif metadata_field.type == MetadataFieldType.DECIMAL:
				validator = QDoubleValidator(-1e12, 1e12, metadata_field.decimal_places, editor)
				validator.setNotation(QDoubleValidator.Notation.StandardNotation)
				editor.setValidator(validator)

			values = [item.metadata.get(metadata_field.id) for item in self._items]
			values_match = bool(values) and all(value == values[0] for value in values[1:])
			if all(metadata_field.id in item.metadata for item in self._items) and values_match:
				editor.setText(self._formatMetadataValue(values[0], metadata_field))
			else:
				editor.setPlaceholderText("Multiple values" if not values_match else "Unset")
			editor.editingFinished.connect(
				lambda field=metadata_field, field_editor=editor: self._setMetadataField(field, field_editor)
			)
			self._form.addRow(metadata_field.name, editor)
			self._metadata_editors.append((metadata_field, editor))

	def _formatMetadataValue(self, value, metadata_field: MetadataField) -> str:
		if metadata_field.type == MetadataFieldType.INTEGER:
			return str(int(value))
		if metadata_field.type == MetadataFieldType.DECIMAL:
			return f"{float(value):.{metadata_field.decimal_places}f}"
		return str(value)

	def _setMetadataField(self, metadata_field: MetadataField, editor: QLineEdit) -> None:
		if not self._items:
			return
		text = editor.text().strip()
		if not text:
			value = None
		else:
			try:
				if metadata_field.type == MetadataFieldType.INTEGER:
					value = int(text)
				elif metadata_field.type == MetadataFieldType.DECIMAL:
					value = float(text)
				else:
					value = text
			except ValueError:
				self._scheduleRefresh()
				return

		for item in self._items:
			if value is None:
				item.metadata.pop(metadata_field.id, None)
			else:
				item.metadata[metadata_field.id] = value
		if self._activity is not None:
			self._activity.changed.emit()


	def _selectLabel(self, index: int) -> None:
		if not self._items:
			return
		label_id = self._label.itemData(index)
		if all(item.label_id == label_id for item in self._items):
			return
		for item in self._items:
			item.label_id = label_id
		if self._activity is not None:
			self._activity.changed.emit()
		self._scheduleRefresh()

	def _setLabelFromText(self) -> None:
		if not self._items:
			return
		name = self._label.currentText().strip()
		if not name:
			return
		index = self._label.currentIndex()
		if index >= 0 and self._label.itemText(index) == name:
			self._selectLabel(index)
			return
		label_set = self._app.labelSet()
		label = label_set.label_named(name) if label_set is not None else None
		if label is None:
			QMessageBox.warning(self, "Unknown Label", f"No active label named '{name}' exists in the selected label set.")
			self._scheduleRefresh()
			return
		self._selectLabel(self._label.findData(label.id))


	def _setPosition(self, axis: str, value: float) -> None:
		if not self._items:
			return

		delta = value - self._values[axis]
		for item in self._items:
			if axis == "x":
				item.setX(item.x() + delta)
			else:
				item.setY(item.y() + delta)
		self._values[axis] = value
		if self._activity is not None:
			self._activity.changed.emit()
