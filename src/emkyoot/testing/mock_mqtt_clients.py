import json
import time
from pathlib import Path
from typing import override, Dict, Any

from . import MessageEvent
from .message_event import MessageEventKind
from ..message_loop import MessageLoopTimer
from ..message_loop import message_loop
from ..mqtt_client import PahoMqttClientImpl, MqttClientImpl


class RecordingMqttClientImpl(PahoMqttClientImpl):
    def __init__(self):
        super().__init__()
        self.start = time.time()
        self.events: list[MessageEvent] = []

    def get_recorded_events(self):
        return self.events

    @override
    def publish(self, topic: str, payload: Dict[str, Any]):
        super().publish(topic, payload)
        self.events.append(
            MessageEvent(
                MessageEventKind.SEND, time.time() - self.start, topic, payload
            )
        )

    @override
    def _on_message_message_thread(self, client, userdata, msg):
        super()._on_message_message_thread(client, userdata, msg)
        topic = msg.topic
        payload = json.loads(msg.payload)
        self.events.append(
            MessageEvent(
                MessageEventKind.RECV, time.time() - self.start, topic, payload
            )
        )


class PlaybackMqttClientImpl(MqttClientImpl):
    """
    Instead of connecting to an MQTT server, this class will read a recording
    and pass along previously received messages as if they were being received
    now. A recording can be handwritten or recorded with
    RecordingMqttClientImpl.

    It also records this new round of communications. The save_recorded_events
    function can be used to save it for later analysis of correctness.
    """

    def __init__(self, recording: list[MessageEvent]):
        super().__init__()
        self.start = time.time()
        self.recorded_events: list[MessageEvent] = []
        self.playback_events = recording
        self.subscriptions: set[str] = set()
        self.on_connect = lambda a: None
        self.on_message = lambda a, b: None

        self.timer = MessageLoopTimer(self.timer_callback)
        self.next_event_index = 0

        self.cumulative_waits = 0.0
        self.replay_failure = False

    def playback_success(self):
        return not self.replay_failure

    def get_recorded_events(self):
        return self.recorded_events

    @override
    def connect(
        self,
        host: str,
        port: int,
        keepalive: int,
        use_tls: bool = False,
        username: str | None = None,
        password: str | None = None,
    ):
        pass

    @override
    def set_on_connect(self, callback):
        self.on_connect = callback

    @override
    def set_on_message(self, callback):
        self.on_message = callback

    @override
    def subscribe(self, topic: str):
        self.subscriptions.add(topic)

    @override
    def publish(self, topic: str, payload: Dict[str, Any]):
        event = MessageEvent(MessageEventKind.SEND, self.get_time(), topic, payload)
        self.recorded_events.append(event)

    def get_time(self):
        return time.time() - self.start

    def timer_callback(self, timer: MessageLoopTimer):
        timer.stop()
        self.prepare_next_callback()

    def check_condition(self):
        next_event = self.playback_events[self.next_event_index]
        prior_event_index = self.next_event_index - 1

        if prior_event_index < 0:
            return True

        prior_event = self.playback_events[prior_event_index]

        for recorded_event in self.recorded_events[::-1]:
            if prior_event.satisfied_by(recorded_event):
                return True

        return False

    def prepare_next_callback(self):
        t = self.get_time()

        while True:
            if self.next_event_index >= len(self.playback_events):
                message_loop.stop()
                return False

            next_event = self.playback_events[self.next_event_index]

            if next_event.kind == MessageEventKind.SEND:
                self.next_event_index += 1
                continue

            if next_event.time < t:
                # Try to match with ignoring base topic as well
                if next_event.topic in self.subscriptions:
                    if next_event.kind == MessageEventKind.CONDITIONAL_RECV:
                        if not self.check_condition():
                            self.cumulative_waits += 0.1

                            if self.cumulative_waits > 1.0:
                                self.replay_failure = True
                                message_loop.stop()
                                return False

                            self.timer.start(0.1)
                            break

                    self.recorded_events.append(
                        MessageEvent(
                            MessageEventKind.RECV,
                            t,
                            next_event.topic,
                            next_event.payload,
                        )
                    )
                    self.on_message(next_event.topic, next_event.payload)

                self.next_event_index += 1
            else:
                self.timer.start(next_event.time - t + 0.1)
                break

        return True

    @override
    def loop_forever(self):
        self.on_connect(100)

        if self.prepare_next_callback():
            message_loop.run()
