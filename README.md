# DLii Labeler

This is a new labeling tool for object detection and object segmentation in videos.

## Setup

### Windows installer

Download `dlii-labeler-windows.msi` from the GitHub release and run it.
It installs for the current user, with a Start menu shortcut. On the feature
selection screen, select **DLii Labeler** to change the installation folder.
Optionally enable **Add to PATH** by choosing **Will be installed on local hard
drive** for that feature (it is off by default).

After enabling PATH, open a new terminal and run:

```powershell
dlii_labeler "C:\path\to\frames"
```

Uninstalling removes the application's PATH entry. The portable Windows ZIP
remains available if you do not want an installer.

### From source

Use Python 3.13 or newer. Install the labeler with

```bash
pip install -e .
```

## Usage

### Command-line export

Export a saved project without opening the GUI:

```bash
dlii_labeler export yolo --type detection ./frames ./output
dlii_labeler export tngo --type segmentation --include-empty-frames ./frames
python3 -m dlii_labeler export yolo --help
```

The project folder contains the images and `.dlii_labels` directory. The optional
output directory defaults to `PROJECT/exports/yolo` or `PROJECT/exports/tngo`.
Each exporter defines its own options, listed by `export FORMAT --help`.
`--type` is inferred when only one annotation type exists; projects containing
both boxes and polygons require an explicit type. `--allow-unassigned` exports
unassigned objects with class ID `-1`; otherwise these cause an error.
Exports include `metadata.json`, use saved changes only, and do not save the
project. Existing output files with matching names are overwritten.

### Graphical interface

Run the labeler with

```bash
python3 -m dlii_labeler </path/to/frames/folder>
```

Save the current project with **File → Save Project** or **Ctrl+S** (**Command+S**
on macOS). Changes stay in memory until you save to the frame folder's
`.dlii_labels` directory. The window indicates unsaved changes and prompts to
save, discard, or cancel before closing or opening another project.

Use **Edit → Undo/Redo** with the standard **Ctrl/Command+Z** and redo shortcuts
to undo annotations, property changes, keyframes, perspective planes, and
scrubber groups/order. Each edit returns to the frame where it was made when
undone or redone. Frame navigation, selection, zoom, and scrolling do not enter
history. Drags and bulk edits are single operations. History holds the latest
100 operations for the open project and resets when a project is opened.

For a polygon linked to a perspective plane, hold **Ctrl** (or **Command** on
macOS) and drag to move it without changing its shape or size. A regular drag
continues to move it through the plane's perspective transform.

In the scrubber, drag the top ruler to change frames and drag across detection
rows to box select keyframes. Drag a diamond to move its keyframe. Use a trackpad
pinch or **Ctrl/Command + mouse wheel** to zoom. Right-click a row or group to
sort or organize detections into groups. In the name column, **Shift-click**
selects a range, **Ctrl/Command-click** toggles one detection, and dragging
selected names reorders them or moves them into a group.

## Building

Install the development dependencies and build a native executable with
PyInstaller using Python 3.13 or newer:

```bash
python -m pip install -e ".[dev]"
python scripts/build.py
```

The output is written to `dist/`. Use `--onedir` for a directory bundle or
`--console` to keep a console window attached for diagnosing packaged builds.
Windowed macOS builds automatically use the native `.app` bundle format.
PyInstaller builds for the operating system on which it runs; the GitHub
Actions workflow builds Linux, macOS, and Windows artifacts when a `v*` tag is
pushed, or when **Release applications** is run manually from the Actions tab.
Tag builds attach the archives and Windows MSI to a GitHub release; manual
builds make them available as workflow artifacts.

The Windows job uses WiX 5.0.2 to package the executable as a per-user MSI and
tests installation both with and without PATH enabled, command discovery, and
uninstallation. The installer version comes from `project.version` in
`pyproject.toml`; increment it before tagging a new release so Windows Installer
can upgrade existing installations.
