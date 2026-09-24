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

Run the labeler with

```bash
python3 -m dlii_labeler </path/to/frames/folder>
```

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
