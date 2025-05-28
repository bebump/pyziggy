import os
import sys
import unittest
from pathlib import Path
from typing import override

from emkyoot import workarounds
from emkyoot.testing import MessageEvent
from emkyoot.testing import PlaybackMqttClientImpl
from emkyoot.util.util import TimedRunner
from generate import create_and_get_devices_client


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


class TestStringMethods(unittest.TestCase):
    def setUp(self):
        self.devices_client_dir = create_and_get_devices_client()
        sys.path.append(self.devices_client_dir.parent)

    def test_simple_automation(self):
        from emkyoot_autogenerate.available_devices import AvailableDevices

        playback_impl = PlaybackMqttClientImpl(
            MessageEvent.load(rel_to_py("resources", "t1.log"))
        )
        devices = AvailableDevices(impl=playback_impl)

        class Test(TimedRunner):
            @override
            def run(self):
                if self.wait(2):
                    devices.tokabo.brightness.set_normalized(1)
                    devices.tokabo.color_temp.set(454)

                if self.wait(1):
                    devices.tokabo.state.set(1)

                if self.wait(1):
                    devices.tokabo.state.set(0)

                if self.wait(1):
                    devices.tokabo.color_temp.set(179)

                if self.wait(1):
                    devices.tokabo.state.set(1)

                if self.wait(1):
                    devices.tokabo.color_temp.set(255)

                if self.wait(1):
                    devices.tokabo.brightness.query_device()

        test = Test(devices)
        devices._set_skip_initial_query(True)
        workarounds._apply(devices)
        devices._connect("", 0, 0, "zigbee2mqtt")
        devices._loop_forever()

        self.assertTrue(playback_impl.playback_success())


if __name__ == "__main__":
    unittest.main()
