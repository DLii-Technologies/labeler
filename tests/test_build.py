"""Run with: python -m unittest discover -s tests -p test_build.py"""

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import sys
import types

spec = importlib.util.spec_from_file_location(
    "build", Path(__file__).resolve().parents[1] / "scripts" / "build.py"
)
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


class BuildTest(TestCase):
    def test_old_python_fails_before_removing_artifacts(self):
        with patch.object(sys, "argv", ["build.py"]), \
             patch.object(sys, "version_info", (3, 12)), \
             patch.object(build.shutil, "rmtree") as remove, \
             patch.object(build, "run") as run:
            with self.assertRaises(SystemExit) as error:
                build.main()
            self.assertEqual(error.exception.code, 2)
            remove.assert_not_called()
            run.assert_not_called()

    def test_build_uses_current_python_and_collects_backends(self):
        with TemporaryDirectory() as directory, \
             patch.object(build, "ROOT", Path(directory)), \
             patch.object(sys, "argv", ["build.py", "--console"]), \
             patch.object(sys, "version_info", (3, 13)), \
             patch.dict(sys.modules, {"dbm.sqlite3": types.ModuleType("dbm.sqlite3")}), \
             patch.object(build, "run") as run:
            self.assertEqual(build.main(), 0)
            command = run.call_args.args[0]
            self.assertEqual(command[:3], [sys.executable, "-m", "PyInstaller"])
            self.assertEqual(command[command.index("--collect-submodules") + 1], "dbm")
