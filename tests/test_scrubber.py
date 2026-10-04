import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QContextMenuEvent, QImage, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QInputDialog, QMenu

from dlii_labeler.application import Application
from dlii_labeler.activity.object_detection_activity import BoxItem, ObjectDetectionActivity
from dlii_labeler.widget.scrubber import Scrubber
from dlii_labeler.widget.object_properties_widget import ObjectPropertiesWidget
from dlii_labeler.data_store import DataStore
from dlii_labeler.label_sets import Label, LabelSet, MetadataField


class ScrubberTest(unittest.TestCase):
	def test_multiselection_survives_visibility_and_edits_shared_properties(self):
		app = Application.instance() or Application([])
		label = Label.create("Pothole")
		field = MetadataField.create("Condition")
		label.fields.append(field)
		other_label = Label.create("Other")
		label_set = LabelSet("test", "Test", [label, other_label])
		with tempfile.TemporaryDirectory() as folder, patch.object(app, "labelSet", return_value=label_set):
			for frame in range(12):
				QImage(20, 20, QImage.Format.Format_RGB32).save(str(Path(folder) / f"{frame:02}.png"))
			app.mediaManager().setFolder(folder)
			scene = app.activities()[ObjectDetectionActivity.IDENTIFIER]
			items = []
			for start, x in [(2, 1), (6, 9)]:
				app.mediaManager().setIndex(start)
				item = BoxItem(QRectF(x, 3, 4, 4))
				item.label_id = label.id
				item.metadata[field.id] = str(x)
				scene.addItem(item)
				item.insertKeyframe()
				app.mediaManager().setIndex(start + 2)
				item.insertKeyframe()
				items.append(item)
			first, second = items
			first.plane_id = "different-plane"
			app.mediaManager().setIndex(3)
			scrubber = Scrubber()
			scrubber.resize(600, 180)
			scrubber.setActivity(scene)
			properties = ObjectPropertiesWidget()
			properties.setActivity(scene)
			scrubber.show()
			properties.show()
			try:
				app.processEvents()
				def point(index):
					return QPoint(50, scrubber.RULER_HEIGHT + index * scrubber.ROW_HEIGHT + scrubber.ROW_HEIGHT // 2)
				QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point(0))
				QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, pos=point(1))
				app.processEvents()
				self.assertEqual(set(scene.selectedAnnotationItems()), set(items))
				self.assertEqual(scene.selectedItems(), [first])
				self.assertFalse(second.isVisible())
				self.assertIn("Changes apply to all", properties._selection.text())
				self.assertEqual(properties._label.currentText(), "Pothole")
				self.assertEqual(properties._plane.currentIndex(), -1)
				self.assertEqual(properties._plane.placeholderText(), "Mixed")
				self.assertIn("Mixed", properties._x.text())
				self.assertNotIn("Mixed", properties._y.text())
				self.assertEqual(properties._y.value(), 3)
				editor = properties._metadata_editors[0][1]
				self.assertEqual(editor.placeholderText(), "Mixed")
				# Merely leaving a mixed field must not overwrite either value.
				editor.editingFinished.emit()
				properties._x.editingFinished.emit()
				self.assertEqual([item.metadata[field.id] for item in items], ["1", "9"])
				self.assertEqual([item.x() for item in items], [1, 9])
				with patch.object(properties, "_clearMetadataFields", wraps=properties._clearMetadataFields) as rebuild:
					app.mediaManager().setIndex(7)
					app.processEvents()
					rebuild.assert_not_called()
				self.assertEqual(set(scene.selectedAnnotationItems()), set(items))
				self.assertEqual(scene.selectedItems(), [second])
				self.assertFalse(first.isVisible())
				QTest.keyClicks(editor, "Repaired")
				editor.editingFinished.emit()
				self.assertEqual([item.metadata[field.id] for item in items], ["Repaired"] * 2)
				# Enter the spinbox's existing backing value: editingFinished must still apply it to all.
				value = properties._x.value()
				properties._x.setFocus()
				properties._x.selectAll()
				QTest.keyClicks(properties._x, str(value))
				QTest.keyClick(properties._x, Qt.Key.Key_Return)
				self.assertEqual([item.x() for item in items], [value] * 2)
				self.assertNotIn("Mixed", properties._x.text())
				properties._y.setValue(12)
				self.assertEqual([item.y() for item in items], [12] * 2)
				second.label_id = other_label.id
				properties._refresh()
				self.assertEqual(properties._label.currentIndex(), -1)
				self.assertEqual(properties._label.lineEdit().placeholderText(), "Mixed")
				properties._selectLabel(properties._label.findData(label.id))
				properties._selectPlane(0)
				app.processEvents()
				self.assertEqual([item.label_id for item in items], [label.id] * 2)
				self.assertEqual([item.plane_id for item in items], [None] * 2)
				self.assertEqual(properties._metadata_editors[0][1].text(), "Repaired")
				# Control/Command toggles preserve the other selection, including hidden objects.
				QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, pos=point(0))
				self.assertEqual(len(scene.selectedAnnotationItems()), 1)
				QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.MetaModifier, pos=point(0))
				self.assertEqual(set(scene.selectedAnnotationItems()), set(items))
			finally:
				properties.close()
				scrubber.close()
				scene.clearSelected()
				for item in items:
					scene.removeItem(item)

	def test_row_selection_drag_order_and_group_drop(self):
		app = Application.instance() or Application([])
		with tempfile.TemporaryDirectory() as folder:
			for frame in range(12):
				QImage(20, 20, QImage.Format.Format_RGB32).save(str(Path(folder) / f"{frame:02}.png"))
			app.mediaManager().setFolder(folder)
			app._data_store = DataStore(folder)
			scene = app.activities()[ObjectDetectionActivity.IDENTIFIER]
			items = [BoxItem(QRectF(index, 1, 4, 4)) for index in range(5)]
			for item in items:
				scene.addItem(item)
			scrubber = Scrubber()
			scrubber.resize(600, 240)
			scrubber.setActivity(scene)
			scrubber.show()
			app.processEvents()
			ordered = [item for _group, item in scrubber._entries]
			self.assertEqual(scrubber._rowName(ordered[0], 0), "BoxItem")
			def point(index):
				return QPoint(50, scrubber.RULER_HEIGHT + index * scrubber.ROW_HEIGHT + scrubber.ROW_HEIGHT // 2)
			actions = []
			with patch.object(QMenu, "exec", lambda menu, _pos: actions.extend(action.text() for action in menu.actions())):
				scrubber.contextMenuEvent(QContextMenuEvent(QContextMenuEvent.Reason.Mouse, point(0)))
			self.assertIn("Add Group/Folder...", actions)
			QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point(0))
			QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, pos=point(3))
			self.assertEqual(set(scene.selectedAnnotationItems()), set(ordered[:4]))
			self.assertEqual(set(scene.selectedItems()), set(ordered[:4]))
			QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, pos=point(1))
			self.assertEqual(set(scene.selectedAnnotationItems()), {ordered[0], ordered[2], ordered[3]})
			QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.MetaModifier, pos=point(4))
			self.assertEqual(set(scene.selectedAnnotationItems()), {ordered[0], ordered[2], ordered[3], ordered[4]})
			QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point(0))
			QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, pos=point(2))
			QTest.mousePress(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point(0))
			QTest.mouseMove(scrubber.viewport(), point(4))
			QTest.mouseRelease(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point(4))
			self.assertEqual([item for _group, item in scrubber._entries], [ordered[3], *ordered[:3], ordered[4]])
			scrubber._loadLayout()
			self.assertEqual([item for _group, item in scrubber._entries], [ordered[3], *ordered[:3], ordered[4]])
			with patch.object(QInputDialog, "getText", return_value=("Potholes", True)):
				scrubber._newGroup()
			row = next(index for index, (_group, item) in enumerate(scrubber._entries) if item is ordered[4])
			QTest.mousePress(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point(row))
			QTest.mouseMove(scrubber.viewport(), point(0))
			QTest.mouseRelease(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point(0))
			self.assertIn(ordered[4].timeline_id, scrubber._groups[0]["items"])
			scrubber.close()
			for item in items:
				scene.removeItem(item)
			app._data_store.close()
			app._data_store = None

	def test_hidden_row_selection_and_double_click_jump(self):
		app = Application.instance() or Application([])
		with tempfile.TemporaryDirectory() as folder:
			for frame in range(12):
				QImage(20, 20, QImage.Format.Format_RGB32).save(str(Path(folder) / f"{frame:02}.png"))
			app.mediaManager().setFolder(folder)
			scene = app.activities()[ObjectDetectionActivity.IDENTIFIER]
			app.mediaManager().setIndex(5)
			box = BoxItem(QRectF(1, 1, 4, 4))
			scene.addItem(box)
			box.insertKeyframe()
			app.mediaManager().setIndex(8)
			box.setX(9)
			box.insertKeyframe()
			app.mediaManager().setIndex(0)
			self.assertFalse(box.isVisible())
			scrubber = Scrubber()
			scrubber.resize(600, 180)
			scrubber.setActivity(scene)
			properties = ObjectPropertiesWidget()
			properties.setActivity(scene)
			scrubber.show()
			properties.show()
			app.processEvents()
			point = QPoint(50, scrubber.RULER_HEIGHT + scrubber.ROW_HEIGHT // 2)
			QTest.mouseClick(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point)
			app.processEvents()
			self.assertFalse(box.isVisible())
			self.assertIn(box, scene.selectedAnnotationItems())
			self.assertIn(box, properties._items)
			self.assertEqual(app.mediaManager().index(), 0)
			with patch.object(properties, "_clearMetadataFields", wraps=properties._clearMetadataFields) as rebuild:
				app.mediaManager().setIndex(8)
				app.processEvents()
				rebuild.assert_not_called()
			self.assertTrue(properties._details.isVisible())
			self.assertEqual(properties._x.value(), 9)
			app.mediaManager().setIndex(0)
			QTest.mouseDClick(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point)
			self.assertEqual(app.mediaManager().index(), 5)
			self.assertTrue(box.isVisible())
			app.mediaManager().setIndex(11)
			self.assertFalse(box.isVisible())
			QTest.mouseDClick(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=point)
			self.assertEqual(app.mediaManager().index(), 8)
			scrubber.close()
			properties.close()
			scene.removeItem(box)

	def test_keyframe_drag_keeps_other_keys_and_frame_bounds(self):
		app = Application.instance() or Application([])
		with tempfile.TemporaryDirectory() as folder:
			for frame in range(12):
				QImage(20, 20, QImage.Format.Format_RGB32).save(str(Path(folder) / f"{frame:02}.png"))
			app.mediaManager().setFolder(folder)
			app._data_store = DataStore(folder)
			scene = app.activities()[ObjectDetectionActivity.IDENTIFIER]
			box = BoxItem(QRectF(1, 1, 4, 4))
			scene.addItem(box)
			box.insertKeyframe()
			app.mediaManager().setIndex(5)
			box.insertKeyframe()
			scrubber = Scrubber()
			scrubber.resize(600, 180)
			scrubber.setActivity(scene)
			scrubber.show()
			app.processEvents()
			self.assertEqual(scrubber._rows, [box])
			self.assertEqual(scrubber._zoom_factor, 1.0)
			self.assertAlmostEqual(scrubber._pixels_per_frame, scrubber._minimumScale())
			self.assertEqual(scrubber.horizontalScrollBar().maximum(), 0)

			y = scrubber.RULER_HEIGHT + scrubber.ROW_HEIGHT // 2
			start = QPoint(round(scrubber._x(5)), y)
			end = QPoint(round(scrubber._x(7)), y)
			QTest.mousePress(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=start)
			QTest.mouseMove(scrubber.viewport(), end)
			QTest.mouseRelease(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=end)
			self.assertEqual(set(box._keyframes), {0, 7})
			self.assertIn((box, 7), scrubber._selected)
			self.assertFalse(box.moveKeyframes({7}, -7))  # occupied frame
			self.assertFalse(box.moveKeyframes({7}, 5))   # past last frame

			# A row drag selects keys; only the ruler changes the current frame.
			app.mediaManager().setIndex(5)
			start = QPoint(round(scrubber._x(6) - 8), y - 10)
			end = QPoint(round(scrubber._x(8) + 8), y + 10)
			QTest.mousePress(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=start)
			QTest.mouseMove(scrubber.viewport(), end)
			QTest.mouseRelease(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=end)
			self.assertIn((box, 7), scrubber._selected)
			self.assertEqual(app.mediaManager().index(), 5)
			self.assertEqual(scene.selectedAnnotationItems(), [box])
			self.assertTrue(box.isSelected())
			QTest.mousePress(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(round(scrubber._x(3)), 12))
			QTest.mouseMove(scrubber.viewport(), QPoint(round(scrubber._x(4)), 12))
			QTest.mouseRelease(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(round(scrubber._x(4)), 12))
			self.assertEqual(app.mediaManager().index(), 4)
			app.mediaManager().setIndex(5)

			scrubber._zoomAt(300, 2.0)
			before_pinch = scrubber._pixels_per_frame
			pinch_frame = (300 - scrubber.LABEL_WIDTH + scrubber.horizontalScrollBar().value()) / before_pinch
			class Pinch:
				def type(self): return QEvent.Type.NativeGesture
				def gestureType(self): return Qt.NativeGestureType.ZoomNativeGesture
				def globalPosition(self): return QPointF(scrubber.viewport().mapToGlobal(QPoint(300, 20)))
				def value(self): return 0.25
				def accept(self): pass
			self.assertTrue(scrubber.viewportEvent(Pinch()))
			self.assertGreater(scrubber._pixels_per_frame, before_pinch)
			self.assertAlmostEqual(
				(300 - scrubber.LABEL_WIDTH + scrubber.horizontalScrollBar().value()) / scrubber._pixels_per_frame,
				pinch_frame, delta=0.02,
			)
			wheel_frame = (350 - scrubber.LABEL_WIDTH + scrubber.horizontalScrollBar().value()) / scrubber._pixels_per_frame
			wheel = QWheelEvent(
				QPointF(0, 20), QPointF(scrubber.viewport().mapToGlobal(QPoint(350, 20))),
				QPoint(), QPoint(0, 120), Qt.MouseButton.NoButton,
				Qt.KeyboardModifier.ControlModifier, Qt.ScrollPhase.NoScrollPhase, False,
			)
			scrubber.wheelEvent(wheel)
			self.assertAlmostEqual(
				(350 - scrubber.LABEL_WIDTH + scrubber.horizontalScrollBar().value()) / scrubber._pixels_per_frame,
				wheel_frame, delta=0.02,
			)
			QTest.qWait(350)
			saved_zoom = scrubber._zoom_factor
			self.assertAlmostEqual(app.dataStore().get(scrubber.LAYOUT_KEY)["zoom"], saved_zoom)
			scrubber._zoom_factor = 1.0
			scrubber._updateScrollbars()
			scrubber._loadLayout()
			self.assertAlmostEqual(scrubber._zoom_factor, saved_zoom)
			scrubber.resize(720, 180)
			app.processEvents()
			self.assertAlmostEqual(scrubber._pixels_per_frame / scrubber._minimumScale(), saved_zoom)
			scrubber.horizontalScrollBar().setValue(100)
			scroll = scrubber.horizontalScrollBar().value()
			QTest.qWait(350)
			self.assertAlmostEqual(
				app.dataStore().get(scrubber.LAYOUT_KEY)["scroll_frame"],
				scroll / scrubber._pixels_per_frame,
			)
			scrubber.horizontalScrollBar().setValue(0)
			scrubber._loadLayout()
			self.assertEqual(scrubber.horizontalScrollBar().value(), scroll)
			QTest.keyClick(scrubber, Qt.Key.Key_Right)
			self.assertEqual(app.mediaManager().index(), 6)
			self.assertEqual(scrubber.horizontalScrollBar().value(), scroll)
			QTest.keyClick(scrubber, Qt.Key.Key_Up)
			self.assertEqual(app.mediaManager().index(), 5)
			self.assertEqual(scrubber.horizontalScrollBar().value(), scroll)

			with patch.object(QInputDialog, "getText", return_value=("Objects", True)):
				scrubber._newGroup(box)
			self.assertEqual(scrubber._entries[0][1], None)
			self.assertEqual(scrubber._entries[1][1], box)
			scrubber._groups.clear()
			scrubber._loadLayout()
			self.assertEqual(scrubber._groups[0]["name"], "Objects")
			scrubber._assignGroup(box, None)
			self.assertIn((None, box), scrubber._entries)
			other = BoxItem(QRectF(7, 7, 4, 4))
			scene.addItem(other)
			scene.changed.emit()
			scrubber._moveRow(other, -1)
			self.assertEqual(scrubber._entries[1][1], other)
			scrubber._assignGroup(other, scrubber._groups[0]["id"])
			self.assertEqual(scrubber._entries[1][1], other)
			self.assertIn((None, box), scrubber._entries)
			extra = [BoxItem(QRectF(1, 1, 4, 4)) for _ in range(10)]
			for item in extra:
				scene.addItem(item)
			scene.changed.emit()
			scrubber.verticalScrollBar().setValue(56)
			vertical_scroll = scrubber.verticalScrollBar().value()
			self.assertGreater(vertical_scroll, 0)
			QTest.qWait(350)
			self.assertEqual(app.dataStore().get(scrubber.LAYOUT_KEY)["scroll_y"], vertical_scroll)
			scrubber.verticalScrollBar().setValue(0)
			scrubber._loadLayout()
			self.assertEqual(scrubber.verticalScrollBar().value(), vertical_scroll)
			scrubber.grab()  # paint path
			scrubber.close()
			scene.removeItem(box)
			scene.removeItem(other)
			for item in extra:
				scene.removeItem(item)
			app._data_store.close()
			app._data_store = None


if __name__ == "__main__":
	unittest.main()
