import os
import sys
import unittest
from pathlib import Path
from typing import override, Type

from emkyoot import workarounds
from emkyoot.testing import MessageEvent
from emkyoot.testing import PlaybackMqttClientImpl, RecordingMqttClientImpl
from emkyoot.testing import create_connection_ascii_art
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


def create_test_ascii_art(client_impl: PlaybackMqttClientImpl) -> str:
    return create_connection_ascii_art(
        client_impl.playback_events.events,
        client_impl.recorded_events.events,
        client_impl.matched_index_pairs,
    )


devices_client_generated = False


def ensure_devices_client_setup():
    global devices_client_generated

    if not devices_client_generated:
        devices_client_dir = create_and_get_devices_client()
        sys.path.append(devices_client_dir.parent)


def connect_to_mqtt_and_record_traffic(automation_class: Type[TimedRunner]):
    ensure_devices_client_setup()

    from emkyoot_autogenerate.available_devices import AvailableDevices

    recording_mqtt_impl = RecordingMqttClientImpl()
    devices = AvailableDevices(impl=recording_mqtt_impl)
    devices._set_skip_initial_query(True)
    workarounds._apply(devices)
    devices._connect("192.168.1.56", 1883, 60, "zigbee2mqtt")
    _ = automation_class(devices)
    devices._loop_forever()

    output_path = rel_to_py("test_logs", f"{automation_class.__name__}.txt")
    print(f"Saving traffic log to {output_path.as_posix()}")
    MessageEvent.dump(recording_mqtt_impl.get_recorded_events(), output_path)


def test_automation_with_mock_mqtt_connection(automation_class: Type[TimedRunner]):
    ensure_devices_client_setup()

    from emkyoot_autogenerate.available_devices import AvailableDevices

    playback_impl = PlaybackMqttClientImpl(
        MessageEvent.load(rel_to_py("resources", f"{automation_class.__name__}.txt"))
    )
    devices = AvailableDevices(impl=playback_impl)
    devices._set_skip_initial_query(True)
    workarounds._apply(devices)
    devices._connect("", 0, 0, "zigbee2mqtt")
    _ = automation_class(devices)
    devices._loop_forever()

    test_build_dir = rel_to_py("test_logs")
    test_build_dir.mkdir(exist_ok=True)
    filename = f"{automation_class.__name__}.txt"

    print(
        f"Saving {automation_class.__name__} test report in {(test_build_dir / filename).as_posix()}"
    )

    with open(test_build_dir / filename, "w") as file:
        file.write(create_test_ascii_art(playback_impl))

    return playback_impl.playback_success()


class TestStringMethods(unittest.TestCase):
    def setUp(self):
        ensure_devices_client_setup()

    def test_simple_automation(self):
        from emkyoot_autogenerate.available_devices import AvailableDevices

        class SimpleAutomation(TimedRunner):
            def __init__(self, devices: AvailableDevices):
                super().__init__(devices)
                self.devices = devices

            @override
            def run(self):
                devices = self.devices

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

        # Uncomment this line if you'd like to actually connect to an MQTT server, execute the
        # automation, record the traffic, and save it to a file.
        # connect_to_mqtt_and_record_traffic(SimpleAutomation)

        # Uncomment this line if you'd like to run the automation with a mock MQTT client
        # implementation that plays back events from a previously recorded traffic log file.
        # The traffic log file can be edited in ways to expect (EXPO, EXPU) or prohibit (PROH)
        # messages sent by the DevicesClient.
        self.assertTrue(test_automation_with_mock_mqtt_connection(SimpleAutomation))


if __name__ == "__main__":
    unittest.main()
