import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt
from PyQt6.QtGui import QImage
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsView, QInputDialog, QMessageBox

from dlii_labeler.application import Application
from dlii_labeler.activity.object_detection_activity import BoxItem, ObjectDetectionActivity
from dlii_labeler.activity.object_segmentation_activity import PathItem, ObjectSegmentationActivity
from dlii_labeler.widget.object_properties_widget import ObjectPropertiesWidget
from dlii_labeler.widget.scrubber import Scrubber


class OperationTest(unittest.TestCase):
	def setUp(self):
		self.app = Application.instance() or Application([])
		self.folder = tempfile.TemporaryDirectory()
		for frame in range(10):
			QImage(100, 100, QImage.Format.Format_RGB32).save(str(Path(self.folder.name) / f"{frame:02}.png"))
		self.app.openFolder(self.folder.name)
		self.scene = self.app.activities()[ObjectDetectionActivity.IDENTIFIER]
		self.history = self.app._operations
		self.widgets = []

	def tearDown(self):
		for widget in self.widgets:
			widget.close()
		self.app._data_store = None
		self.history.stack.clear()
		self.app.perspectivePlanes()._planes.clear()
		self.app.perspectivePlanes().updated.emit()
		for scene in self.app.activities().values():
			scene.clear()
		self.folder.cleanup()

	def boxes(self):
		return [item for item in self.scene.items() if isinstance(item, BoxItem)]

	def test_edit_frames_creation_deletion_and_redo_branch(self):
		self.app.mediaManager().setIndex(2)
		self.scene.createBox(QRectF(10, 10, 20, 20))
		item = self.boxes()[0]
		item_id = item.timeline_id
		self.assertEqual(self.history.stack.count(), 1)
		self.app.mediaManager().setIndex(7)
		self.scene.clearSelected()
		self.scene.setTimelineSelection([item])
		self.assertEqual(self.history.stack.count(), 1)
		self.history.undo()
		self.assertEqual(self.app.mediaManager().index(), 2)
		self.assertEqual(self.boxes(), [])
		self.app.mediaManager().setIndex(9)
		self.history.redo()
		self.assertEqual(self.app.mediaManager().index(), 2)
		item = self.boxes()[0]
		self.assertEqual(item.timeline_id, item_id)
		self.assertTrue(item.isSelected())
		self.app.mediaManager().setIndex(5)
		self.scene.deleteSelected()
		self.assertEqual(self.history.stack.count(), 2)
		self.app.mediaManager().setIndex(8)
		self.history.undo()
		self.assertEqual(self.app.mediaManager().index(), 5)
		self.assertEqual(len(self.boxes()), 1)
		self.scene.createBox(QRectF(40, 40, 20, 20))
		self.assertFalse(self.history.stack.canRedo())
		self.assertEqual(len(self.boxes()), 2)

	def test_bulk_properties_keyframes_and_manual_save(self):
		self.scene.createBox(QRectF(10, 10, 20, 20))
		self.scene.createBox(QRectF(40, 10, 20, 20))
		items = self.boxes()
		self.scene.setTimelineSelection(items)
		self.app.mediaManager().setIndex(3)
		self.scene.insertKeyframe()
		self.assertEqual(self.history.stack.count(), 3)
		self.app.mediaManager().setIndex(7)
		self.scene.insertKeyframe()
		properties = ObjectPropertiesWidget()
		self.widgets.append(properties)
		properties.setActivity(self.scene)
		self.app.mediaManager().setIndex(5)
		self.app.processEvents()
		before = [item.x() for item in items]
		properties._setPosition("x", 25)
		self.assertEqual(self.history.stack.count(), 5)
		properties._setPosition("x", 25)  # No-op edits do not grow history.
		self.assertEqual(self.history.stack.count(), 5)
		self.app.mediaManager().setIndex(9)
		self.history.undo()
		self.assertEqual(self.app.mediaManager().index(), 5)
		self.assertEqual([item.x() for item in items], before)
		self.history.redo()
		self.assertEqual([item.x() for item in items], [25, 25])
		self.assertTrue(self.app.dataStore().isModified())
		self.assertFalse((Path(self.folder.name) / ".dlii_labels").exists())
		self.assertTrue(self.app.saveProject())
		self.assertTrue(self.history.stack.isClean())
		self.history.undo()
		self.assertTrue(self.app.dataStore().isModified())
		self.history.undo()
		self.assertEqual(self.app.mediaManager().index(), 7)
		self.assertEqual([set(item._keyframes) for item in items], [{3}, {3}])
		with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Discard):
			self.app.openFolder(self.folder.name)
		self.assertEqual(self.history.stack.count(), 0)
		self.assertEqual(len(self.boxes()), 2)

	def test_canvas_drag_is_one_operation_and_restores_polygon_vertices(self):
		self.scene.createBox(QRectF(20, 20, 50, 50))
		item = self.boxes()[0]
		view = QGraphicsView(self.scene)
		self.widgets.append(view)
		view.resize(400, 400)
		view.show()
		self.app.processEvents()
		self.app.mediaManager().setIndex(4)
		before = item.pos()
		start = view.mapFromScene(QPointF(40, 40))
		finish = view.mapFromScene(QPointF(50, 55))
		QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
		QTest.mouseMove(view.viewport(), finish)
		QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=finish)
		self.assertNotEqual(item.pos(), before)
		self.assertEqual(self.history.stack.count(), 2)
		self.app.mediaManager().setIndex(8)
		self.history.undo()
		self.assertEqual(self.app.mediaManager().index(), 4)
		self.assertEqual(item.pos(), before)
		segmentation = self.app.activities()[ObjectSegmentationActivity.IDENTIFIER]
		segmentation.createPath([QPointF(10, 10), QPointF(50, 10), QPointF(40, 40)])
		path = next(item for item in segmentation.items() if isinstance(item, PathItem))
		path.point_ids = [3, 8, 12]
		with self.history.operation("Edit polygon vertices"):
			path.points.insert(1, QPointF(20, 0))
			path.point_ids.insert(1, 15)
			path._rebuildPath()
			segmentation.geometryChanged.emit()
		self.history.undo()
		self.assertEqual(path.point_ids, [3, 8, 12])
		self.history.redo()
		self.assertEqual(path.point_ids, [3, 15, 8, 12])
		self.assertEqual(path._next_point_id, 16)

	def test_polygon_selection_does_not_move_geometry(self):
		scene = self.app.activities()[ObjectSegmentationActivity.IDENTIFIER]
		scene.createPath([QPointF(20, 20), QPointF(80, 20), QPointF(80, 80), QPointF(20, 80)])
		item = next(item for item in scene.items() if isinstance(item, PathItem))
		view = QGraphicsView(scene)
		properties = ObjectPropertiesWidget()
		properties.setActivity(scene)
		self.widgets.extend([view, properties])
		view.resize(400, 400)
		view.scale(2, 2)
		view.show()
		properties.show()
		self.app.processEvents()
		plane = self.app.perspectivePlanes().create()
		for plane_id in (None, plane.id):
			item.plane_id = plane_id
			for transform_mode in (False, True):
				item._transform_mode = transform_mode
				for location in (QPointF(20, 50), QPointF(20, 20)):
					for modifiers in (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier):
						scene.setTimelineSelection([])
						self.app.processEvents()
						before = item.currentState()
						count = self.history.stack.count()
						QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, modifiers, view.mapFromScene(location))
						self.app.processEvents()
						self.assertTrue(item.isSelected())
						self.assertEqual(item.currentState(), before)
						self.assertEqual(self.history.stack.count(), count)

	def test_planes_and_groups_restore_without_changing_zoom(self):
		self.scene.createBox(QRectF(10, 10, 20, 20))
		item = self.boxes()[0]
		plane = self.app.perspectivePlanes().create()
		item.plane_id = plane.id
		self.app.mediaManager().setIndex(6)
		self.app.perspectivePlanes().remove(plane.id)
		self.assertIsNone(item.plane_id)
		self.app.mediaManager().setIndex(9)
		self.history.undo()
		self.assertEqual(self.app.mediaManager().index(), 6)
		self.assertEqual(item.plane_id, plane.id)
		self.assertIsNotNone(self.app.perspectivePlanes().get(plane.id))
		scrubber = Scrubber()
		self.widgets.append(scrubber)
		scrubber.setActivity(self.scene)
		with patch.object(QInputDialog, "getText", return_value=("Potholes", True)):
			scrubber._newGroup(item)
		count = self.history.stack.count()
		scrubber._zoomAt(200, 2)
		scrubber._saveLayout()
		zoom = scrubber._zoom_factor
		self.assertEqual(self.history.stack.count(), count)
		self.history.undo()
		self.assertEqual(scrubber._groups, [])
		self.assertEqual(scrubber._zoom_factor, zoom)
		self.history.redo()
		self.assertEqual(scrubber._groups[0]["items"], [item.timeline_id])
		self.assertEqual(scrubber._zoom_factor, zoom)

	def test_timeline_key_drag_uses_edit_frame_not_key_destination(self):
		self.scene.createBox(QRectF(10, 10, 20, 20))
		self.app.mediaManager().setIndex(2)
		self.scene.insertKeyframe()
		self.app.mediaManager().setIndex(6)
		self.scene.insertKeyframe()
		item = self.boxes()[0]
		self.app.mediaManager().setIndex(3)
		scrubber = Scrubber()
		self.widgets.append(scrubber)
		scrubber.resize(600, 180)
		scrubber.setActivity(self.scene)
		scrubber.show()
		self.app.processEvents()
		count = self.history.stack.count()
		y = scrubber.RULER_HEIGHT + scrubber.ROW_HEIGHT // 2
		QTest.mousePress(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(round(scrubber._x(6)), y))
		QTest.mouseMove(scrubber.viewport(), QPoint(round(scrubber._x(8)), y))
		QTest.mouseRelease(scrubber.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(round(scrubber._x(8)), y))
		self.assertEqual(set(item._keyframes), {2, 8})
		self.assertEqual(self.history.stack.count(), count + 1)
		self.app.mediaManager().setIndex(9)
		self.history.undo()
		self.assertEqual(self.app.mediaManager().index(), 3)
		self.assertEqual(set(item._keyframes), {2, 6})
		self.app.mediaManager().setIndex(0)
		self.history.redo()
		self.assertEqual(self.app.mediaManager().index(), 3)
		self.assertEqual(set(item._keyframes), {2, 8})


if __name__ == "__main__":
	unittest.main()
