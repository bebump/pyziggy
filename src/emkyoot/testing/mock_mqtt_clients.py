import json
import time
from pathlib import Path
from typing import override, Dict, Any

from . import MessageEvent
from ..mqtt_client import PahoMqttClientImpl, MqttClientImpl


class RecordingMqttClientImpl(PahoMqttClientImpl):
    def __init__(self):
        super().__init__()
        self.start = time.time()
        self.events: list[MessageEvent] = []

    def save_recorded_events(self, path: Path):
        MessageEvent.dump(self.events, path)

    @override
    def publish(self, topic: str, payload: Dict[str, Any]):
        super().publish(topic, payload)
        self.events.append(
            MessageEvent(False, time.time() - self.start, topic, payload)
        )

    @override
    def _on_message_message_thread(self, client, userdata, msg):
        super()._on_message_message_thread(client, userdata, msg)
        topic = msg.topic
        payload = json.loads(msg.payload)
        self.events.append(MessageEvent(True, time.time() - self.start, topic, payload))


class PlaybackMqttClientImpl(MqttClientImpl):
    """
    Instead of connecting to an MQTT server, this class will read a recording
    and pass along previously received messages as if they were being received
    now. A recording can be handwritten or recorded with
    RecordingMqttClientImpl.

    It also records this new round of communications. The save_recorded_events
    function can be used to save it for later analysis of correctness.
    """

    def __init__(self, recording: Path):
        super().__init__()
        self.start = time.time()
        self.events = MessageEvent.load(recording)
