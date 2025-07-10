import unittest
from pathlib import Path
import os

from pyziggy.run import run_mypy


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


class TestFrameworkMypy(unittest.TestCase):
    def test_framework_mypy(self):
        self.assertTrue(run_mypy(rel_to_py("..", "src", "pyziggy")))
