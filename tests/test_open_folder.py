"""Run with: QT_QPA_PLATFORM=offscreen PYTHONPATH=src python -m unittest discover -s tests"""

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication

from dlii_labeler.application import Application
from dlii_labeler.media_manager import MediaManager


class OpenFolderTest(TestCase):
    def test_empty_folder_preserves_project(self):
        qt_app = QApplication.instance() or QApplication([])
        manager = MediaManager()
        store = Mock()
        app = SimpleNamespace(_media_manager=manager, _data_store=store,
                              _folder_path=Path("existing-project"))
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch("dlii_labeler.application.QMessageBox.warning") as warning:
                self.assertFalse(Application.openFolder(app, folder))
                warning.assert_called_once()
            # Neither nested images nor directories named like images count.
            (folder / "nested.jpg").mkdir()
            (folder / "nested.jpg" / "frame.png").touch()
            (folder / "notes.txt").touch()
            self.assertEqual(manager.scanFolder(folder), [])
            with patch("dlii_labeler.application.QMessageBox.warning"):
                self.assertFalse(Application.openFolder(app, str(folder)))
            self.assertEqual(app._folder_path, Path("existing-project"))
            self.assertIs(app._data_store, store)
            store.close.assert_not_called()
            self.assertIsNone(manager.folder())
            self.assertFalse((folder / ".dlii_labels").exists())
            (folder / "frame.JPG").touch()
            self.assertEqual(manager.scanFolder(folder), [folder / "frame.JPG"])
            manager.setFolder(str(folder))
            self.assertEqual(manager.index(), 0)
            self.assertEqual(manager.length(), 1)
