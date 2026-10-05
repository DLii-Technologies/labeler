import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QCoreApplication, QEvent, QRectF
from PyQt6.QtGui import QImage, QKeySequence
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QMessageBox

from dlii_labeler.application import Application
from dlii_labeler.activity.object_detection_activity import BoxItem, ObjectDetectionActivity
from dlii_labeler.data_store import DataStore
from dlii_labeler.main_window import MainWindow


class ProjectSaveTest(unittest.TestCase):
	def test_store_writes_only_on_explicit_save(self):
		with tempfile.TemporaryDirectory() as folder:
			store = DataStore(folder)
			value = {"objects": [1]}
			store.set("project", value)
			value["objects"].append(2)
			self.assertEqual(store.get("project"), {"objects": [1]})
			self.assertTrue(store.isModified())
			self.assertFalse((Path(folder) / ".dlii_labels").exists())
			store.sync()
			self.assertFalse(store.isModified())
			store.set("project", {"objects": [3]})
			self.assertEqual(DataStore(folder).get("project"), {"objects": [1]})
			store.close()
			self.assertEqual(DataStore(folder).get("project"), {"objects": [1]})

	def test_save_menu_and_unsaved_project_lifecycle(self):
		app = Application.instance() or Application([])
		with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
			for directory in (folder, other):
				QImage(20, 20, QImage.Format.Format_RGB32).save(str(Path(directory) / "frame.png"))
			self.assertTrue(app.openFolder(folder))
			window = MainWindow()
			window.show()
			scene = app.activities()[ObjectDetectionActivity.IDENTIFIER]
			try:
				app.processEvents()
				QTest.qWait(400)  # Include deferred window and scrubber initialization.
				self.assertFalse(app.dataStore().isModified())
				self.assertFalse(window.windowTitle().startswith("● "))
				with patch.object(QMessageBox, "warning") as warning:
					self.assertTrue(app.confirmUnsavedChanges(window))
					warning.assert_not_called()
				item = BoxItem(QRectF(1, 2, 4, 4))
				scene.addItem(item)
				scene.changed.emit()
				self.assertTrue(app.dataStore().isModified())
				self.assertTrue(window.windowTitle().startswith("● "))
				self.assertFalse((Path(folder) / ".dlii_labels").exists())
				self.assertEqual(window._save_action.shortcut(), QKeySequence(QKeySequence.StandardKey.Save))
				window._save_action.trigger()
				self.assertFalse(app.dataStore().isModified())
				self.assertFalse(window.windowTitle().startswith("● "))
				saved = DataStore(folder).get(scene.IDENTIFIER)
				self.assertEqual(len(saved["items"]), 1)
				self.assertTrue(app.openFolder(folder))
				QTest.qWait(400)
				self.assertFalse(app.dataStore().isModified())
				self.assertFalse(window.windowTitle().startswith("● "))
				item = next(item for item in scene.items() if isinstance(item, BoxItem))
				item.metadata["condition"] = "changed"
				scene.changed.emit()
				self.assertEqual(DataStore(folder).get(scene.IDENTIFIER), saved)
				with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Cancel):
					self.assertFalse(window.close())
					self.assertFalse(app.openFolder(other))
				self.assertEqual(app.folderPath(), Path(folder))
				with patch.object(app.dataStore(), "sync", side_effect=OSError("Disk full")), patch.object(QMessageBox, "critical") as error:
					with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Save):
						self.assertFalse(app.openFolder(other))
					error.assert_called_once()
				self.assertTrue(app.dataStore().isModified())
				self.assertEqual(app.folderPath(), Path(folder))
				with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Discard):
					self.assertTrue(app.openFolder(other))
				self.assertEqual(DataStore(folder).get(scene.IDENTIFIER), saved)
				self.assertFalse(any(isinstance(item, BoxItem) for item in scene.items()))
				item = BoxItem(QRectF(3, 4, 4, 4))
				scene.addItem(item)
				scene.changed.emit()
				with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Save):
					self.assertTrue(window.close())
				self.assertEqual(len(DataStore(other).get(scene.IDENTIFIER)["items"]), 1)
			finally:
				with patch.object(app, "confirmUnsavedChanges", return_value=True):
					window.close()
				window.deleteLater()
				QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
				app._data_store = None
				for activity in app.activities().values():
					activity.clear()


if __name__ == "__main__":
	unittest.main()
