# DLii Labeler

This is a new labeling tool for object detection and object segmentation in videos.

## Setup

Install the labeler with

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
PyInstaller:

```bash
pip install -e ".[dev]"
python scripts/build.py
```

The output is written to `dist/`. Use `--onedir` for a directory bundle or
`--console` to keep a console window attached for diagnosing packaged builds.
Windowed macOS builds automatically use the native `.app` bundle format.
PyInstaller builds for the operating system on which it runs; the GitHub
Actions workflow builds Linux, macOS, and Windows artifacts on pushes to
`master`.
