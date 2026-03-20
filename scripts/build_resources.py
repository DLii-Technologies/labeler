import json
import subprocess
from pathlib import Path
import tomllib

OUTPUT_PATH = "./src/dlii_labeler/gen/resources_rc.py"

toml = tomllib.load(open("pyproject.toml", "rb"))

# Build the app manifest
if not Path("./resources/gen").exists():
    Path("./resources/gen").mkdir()
with open("./resources/gen/manifest.json", "w") as f:
    json.dump({
        "name": toml["project"]["name"],
        "display_name": toml["manifest"]["display-name"],
        "version": toml["project"]["version"],
        "organization": toml["manifest"]["organization"],
        "organization_domain": toml["manifest"]["organization-domain"]
    }, f)

subprocess.run(["rcc", "-g", "python", "resources/resources.qrc", "-o", OUTPUT_PATH])

# Need to replace pyside imports with PyQt
OUTPUT_PATH.parent.mkdir(exist_ok=True, parents=True)
with open(OUTPUT_PATH, "r") as f:
    lines = f.readlines()
with open(OUTPUT_PATH, "w") as f:
    for line in lines:
        f.write(line.replace("PySide6", "PyQt6"))
