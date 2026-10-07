"""Command-line entry points for saved projects."""

import argparse
from contextlib import nullcontext
import dbm
import os
from pathlib import Path
import sys


def main(argv=None) -> int:
	from dlii_labeler.export.yolo_exporter import YoloExporter
	from dlii_labeler.export.tngo_exporter import TngoExporter

	parser = argparse.ArgumentParser(prog="dlii_labeler", description="Open the GUI with dlii_labeler PROJECT, or export a saved project.")
	commands = parser.add_subparsers(dest="command", required=True)
	export = commands.add_parser("export", help="Export saved project annotations")
	formats = export.add_subparsers(dest="format", required=True)
	for name, exporter in (("yolo", YoloExporter), ("tngo", TngoExporter)):
		format_parser = formats.add_parser(name, help=f"Export {exporter.IDENTIFIER} annotations")
		exporter.add_cli_arguments(format_parser)
		format_parser.add_argument("--allow-unassigned", action="store_true", help="Export unassigned objects with class ID -1")
		format_parser.add_argument("project", type=Path, help="Image folder containing .dlii_labels")
		format_parser.add_argument("output", type=Path, nargs="?", help="Output directory (default: PROJECT/exports/FORMAT)")
		format_parser.set_defaults(exporter=exporter)
	args = parser.parse_args(argv)
	try:
		project = args.project.resolve()
		if not project.is_dir() or not dbm.whichdb(str(project / ".dlii_labels" / "data")):
			raise ValueError(f"No saved project found in {project}")
		os.environ["QT_QPA_PLATFORM"] = "offscreen"
		from dlii_labeler.application import Application
		app = Application(["dlii_labeler"])
		app.openFolder(project, interactive=False)
		if not app.dataStore().checkVersion():
			print("Warning: project was saved with a different application version.", file=sys.stderr)
		exporter = args.exporter()
		options = exporter.cli_options(args)
		output = args.output.resolve() if args.output else project / "exports" / args.format
		with exporter.allowingUnassigned() if args.allow_unassigned else nullcontext():
			exporter.export(output, options)
		print(f"Exported {args.format.upper()} annotations to {output}")
		return 0
	except Exception as error:
		print(f"Export failed: {error}", file=sys.stderr)
		return 1
