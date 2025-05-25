from emkyoot.generator import generate_devices_client

# Interprets the provided path constituents relative to the location of this
# script, and returns an absolute Path to the resulting location.
#
# E.g. rel_to_py(".") returns an absolute path to the directory containing this
# script.
import json
import os
import shutil
from pathlib import Path


def rel_to_py(*paths) -> Path:
    return Path(
        os.path.realpath(
            os.path.join(os.path.realpath(os.path.dirname(__file__)), *paths)
        )
    )


def create_and_get_devices_client():
    def load_devices_json():
        with open(rel_to_py("resources", "devices.json"), "r") as file:
            return json.load(file)

    devices_json = load_devices_json()

    test_build_dir = rel_to_py("build")

    if test_build_dir.exists():
        shutil.rmtree(test_build_dir)

    test_build_dir.mkdir()

    autogenerate_dir = test_build_dir / "emkyoot_autogenerate"
    autogenerate_dir.mkdir()

    generate_devices_client(devices_json, autogenerate_dir / "available_devices.py")

    return autogenerate_dir
