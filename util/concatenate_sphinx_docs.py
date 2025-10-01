import os
from pathlib import Path


# Interprets the provided path constituents relative to the location of this
# script, and returns an absolute Path to the resulting location.
#
# E.g. rel_to_py(".") returns an absolute path to the directory containing this
# script.
def rel_to_py(*paths) -> Path:
    return Path(
        os.path.realpath(
            os.path.join(os.path.realpath(os.path.dirname(__file__)), *paths)
        )
    )


index_path = rel_to_py("..", "docs", "source", "index.rst")

index_contents: str | None = None

if index_path.exists():
    with open(index_path, "r", encoding="utf-8") as f:
        index_contents = f.read()

if index_contents is None:
    exit(0)

sections = [
    line.strip()
    for line in index_contents.splitlines()
    if line.strip() and not line.strip().startswith((".", ":"))
]

for i, section in enumerate(sections):
    if "<self>" in section:
        sections[i] = "index"

if "api" in sections:
    sections = [s for s in sections if s != "api"] + ["api"]

subdir, ext = "markdown", "md"

build_path = rel_to_py("..", "docs", "build", subdir)


source_files: list[Path] = []

for section in sections:
    source_path = build_path / f"{section}.{ext}"

    if source_path.exists():
        source_files.append(source_path)

generated_dir = build_path / "generated"
if generated_dir.exists() and generated_dir.is_dir():
    for file in sorted(generated_dir.iterdir()):
        if file.is_file():
            source_files.append(file)

concatenated_contents = """This is a pyziggy project directory. What follows is the entire documentation
of the pyziggy package. You can assume that Zigbee2MQTT has been installed
already, so you can ignore the section about Zigbee2MQTT installation.

Pay attention to the section about the "Execution model and the pyziggy runner".

---

"""

for file_path in source_files:
    with open(file_path, "r", encoding="utf-8") as f:
        concatenated_contents += f.read()


print(concatenated_contents)
