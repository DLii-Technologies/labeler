#!/usr/bin/env python3

"""Build a native application with PyInstaller.

PyInstaller does not cross-compile. Run this script on the operating system
for which the executable is needed; the GitHub workflow runs it once per OS.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = ROOT / "src/dlii_labeler/__main__.py"


def run(command: list[str]) -> None:
	print("+", " ".join(command), flush=True)
	subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument(
		"--name",
		default="dlii_labeler",
		help="Executable name (default: dlii_labeler)",
	)
	parser.add_argument(
		"--onedir",
		action="store_true",
		help="Create a directory bundle instead of a single executable",
	)
	parser.add_argument(
		"--console",
		action="store_true",
		help="Keep a console window attached (useful for diagnosing packaged builds)",
	)
	args = parser.parse_args()
	# PyInstaller is deprecating one-file + windowed macOS builds. A directory
	# bundle is the normal macOS application format and produces a .app bundle.
	macos_app = sys.platform == "darwin" and not args.console
	build_mode = "--onedir" if args.onedir or macos_app else "--onefile"
	if macos_app and not args.onedir:
		print("macOS windowed build: creating an onedir .app bundle", flush=True)

	# Avoid leaving an artifact from a previous mode (for example, a stale
	# one-file executable next to a newly created macOS .app bundle).
	dist_path = ROOT / "dist"
	for old_artifact in (
		dist_path / args.name,
		dist_path / f"{args.name}.app",
		dist_path / f"{args.name}.exe",
	):
		if old_artifact.is_dir():
			shutil.rmtree(old_artifact)
		elif old_artifact.exists():
			old_artifact.unlink()

	# Generate the versioned manifest module before PyInstaller analyzes imports.
	run([sys.executable, str(ROOT / "scripts/build_resources.py")])

	pyinstaller = shutil.which("pyinstaller")
	if pyinstaller is not None:
		pyinstaller_command = [pyinstaller]
	else:
		pyinstaller_command = [sys.executable, "-m", "PyInstaller"]

	command = pyinstaller_command + [
		"--noconfirm",
		"--clean",
		"--name",
		args.name,
		"--paths",
		str(ROOT / "src"),
		"--distpath",
		str(ROOT / "dist"),
		"--workpath",
		str(ROOT / "build/pyinstaller"),
		"--specpath",
		str(ROOT / "build"),
		build_mode,
		"--console" if args.console else "--windowed",
		str(ENTRY_POINT),
	]
	run(command)

	print(f"Build complete: {ROOT / 'dist'}", flush=True)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
