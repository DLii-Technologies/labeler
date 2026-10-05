import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CliTest(unittest.TestCase):
	def run_cli(self, *args):
		return subprocess.run([sys.executable, "-m", "dlii_labeler", *map(str, args)], capture_output=True, text=True, timeout=30)

	def test_help_and_missing_project(self):
		for name in ("yolo", "tngo"):
			result = self.run_cli("export", name, "--help")
			self.assertEqual(result.returncode, 0, result.stderr)
			self.assertIn("--include-empty-frames", result.stdout)
		with tempfile.TemporaryDirectory() as folder:
			result = self.run_cli("export", "yolo", folder)
			self.assertEqual(result.returncode, 1)
			self.assertIn("No saved project", result.stderr)

	def test_exports_saved_project_without_modifying_it(self):
		with tempfile.TemporaryDirectory() as folder:
			project = Path(folder)
			setup = '''
import sys
from pathlib import Path
from PyQt6.QtCore import QRectF, QPointF
from PyQt6.QtGui import QImage
from dlii_labeler.application import Application
from dlii_labeler.activity.object_detection_activity import ObjectDetectionActivity
from dlii_labeler.activity.object_segmentation_activity import ObjectSegmentationActivity
app = Application([])
folder = Path(sys.argv[1])
QImage(100, 100, QImage.Format.Format_RGB32).save(str(folder / '000.png'))
app.openFolder(folder)
app.activities()[ObjectDetectionActivity.IDENTIFIER].createBox(QRectF(10, 20, 30, 40))
app.activities()[ObjectSegmentationActivity.IDENTIFIER].createPath([QPointF(10,10), QPointF(50,10), QPointF(20,50)])
app.activities()[ObjectDetectionActivity.IDENTIFIER].insertKeyframe()
app.activities()[ObjectSegmentationActivity.IDENTIFIER].insertKeyframe()
assert app.saveProject()
'''
			result = subprocess.run([sys.executable, "-c", setup, folder], env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, capture_output=True, text=True, timeout=30)
			self.assertEqual(result.returncode, 0, result.stderr)
			before = {p.name: p.read_bytes() for p in (project / ".dlii_labels").iterdir()}
			result = self.run_cli("export", "yolo", project)
			self.assertEqual(result.returncode, 1)
			self.assertIn("choose --type", result.stderr)
			for name in ("yolo", "tngo"):
				for kind in ("detection", "segmentation"):
					output = project / f"{name}-{kind}"
					result = self.run_cli("export", name, "--type", kind, "--allow-unassigned", project, output)
					self.assertEqual(result.returncode, 0, result.stderr)
					fields = (output / "000.txt").read_text().split()
					self.assertEqual(len(fields), (5 if kind == "detection" else 7) + (name == "tngo"))
					self.assertTrue((output / "metadata.json").exists())
			result = self.run_cli("export", "yolo", "--type", "detection", project)
			self.assertEqual(result.returncode, 1)
			self.assertIn("unassigned", result.stderr)
			result = self.run_cli("export", "yolo", "--type", "detection", "--allow-unassigned", project)
			self.assertEqual(result.returncode, 0, result.stderr)
			self.assertTrue((project / "exports/yolo/000.txt").exists())
			self.assertEqual(before, {p.name: p.read_bytes() for p in (project / ".dlii_labels").iterdir()})
