# pyziggy - Run automation scripts that interact with zigbee2mqtt.
# Copyright (C) 2025 Attila Szarvas
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
import time
from typing import override, Dict, Any, Tuple

from . import MessageEvent
from .message_event import MessageEventKind, MessageEventList
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
        self.recorded_events: MessageEventList = MessageEventList()
        self.matching_recorded_event_indices: set[int] = set()
        self.matched_index_pairs: list[Tuple[int, int]] = []
        self.last_matched_event_index = -1
        self.playback_events = MessageEventList(recording)

        if (
            self.playback_events.events
            and self.playback_events.events[-1].kind != MessageEventKind.RECV
        ):
            last_event = self.playback_events.events[-1]
            recv_event = MessageEvent(
                MessageEventKind.RECV,
                last_event.time + 0.1,
                "zigbee2mqtt/INJECTED_TEST_EVENT",
                json.loads("{}"),
            )
            self.playback_events.events.append(recv_event)

        self.next_recv_index: int | None = self.playback_events.get_next_recv_index()
        self.subscriptions: set[str] = set()
        self.on_connect = lambda a: None
        self.on_message = lambda a, b: None

        self.timer = MessageLoopTimer(self.timer_callback)

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
        self.recorded_events.add(event)

    def get_time(self):
        return time.time() - self.start

    def timer_callback(self, timer: MessageLoopTimer):
        timer.stop()
        self.prepare_next_callback()

    def match_expected_messages(
        self, messages: list[MessageEvent], messages_begin: int
    ):
        begin = (
            max(self.matching_recorded_event_indices)
            if self.matching_recorded_event_indices
            else 0
        )
        candidates = self.recorded_events.events[begin:]
        matched_candidate_indices: set[int] = set()

        success = True

        for i_message in reversed(range(len(messages))):
            message = messages[i_message]

            if message.kind != MessageEventKind.EXPECTED_ORDERED:
                continue

            match_found = False

            i_candidate_max = min(
                len(candidates),
                (
                    max(matched_candidate_indices)
                    if matched_candidate_indices
                    else len(candidates)
                ),
            )

            for i_candidate in reversed(range(i_candidate_max)):
                if i_candidate in matched_candidate_indices:
                    continue

                if message.satisfied_by(candidates[i_candidate]):
                    self.matched_index_pairs.append(
                        (i_message + messages_begin, i_candidate + begin)
                    )
                    matched_candidate_indices.add(i_candidate)
                    match_found = True
                    break

            if not match_found:
                success = False

        for i_message in reversed(range(len(messages))):
            message = messages[i_message]

            if message.kind != MessageEventKind.EXPECTED_UNORDERED:
                continue

            match_found = False

            i_candidate_max = len(candidates)

            for i_candidate in reversed(range(i_candidate_max)):
                if i_candidate in matched_candidate_indices:
                    continue

                if message.satisfied_by(candidates[i_candidate]):
                    self.matched_index_pairs.append(
                        (i_message + messages_begin, i_candidate + begin)
                    )
                    matched_candidate_indices.add(i_candidate)
                    match_found = True
                    break

            if not match_found:
                success = False

        for i_message in reversed(range(len(messages))):
            message = messages[i_message]

            if message.kind != MessageEventKind.SEND:
                continue

            i_candidate_max = len(candidates)

            for i_candidate in reversed(range(i_candidate_max)):
                if i_candidate in matched_candidate_indices:
                    continue

                if message.satisfied_by(candidates[i_candidate]):
                    self.matched_index_pairs.append(
                        (i_message + messages_begin, i_candidate + begin)
                    )
                    matched_candidate_indices.add(i_candidate)
                    break

        for i_message in reversed(range(len(messages))):
            message = messages[i_message]

            if message.kind != MessageEventKind.PROHIBITED:
                continue

            i_candidate_max = len(candidates)

            for i_candidate in reversed(range(i_candidate_max)):
                if i_candidate in matched_candidate_indices:
                    continue

                if message.satisfied_by(candidates[i_candidate]):
                    self.matched_index_pairs.append(
                        (i_message + messages_begin, i_candidate + begin)
                    )
                    self.replay_failure = True
                    break

        for i in matched_candidate_indices:
            self.matching_recorded_event_indices.add(i + begin)

        return success

    def prepare_next_callback(self):
        t = self.get_time()

        while True:
            if self.next_recv_index is None:
                message_loop.stop()
                return False

            next_recv_event = self.playback_events.get(self.next_recv_index)

            if next_recv_event.time < t:
                # We need to find a match for these messages before we can proceed
                expected_messages = self.playback_events.get_from_recv_up_to_recv(
                    self.next_recv_index
                )

                if not self.match_expected_messages(
                    expected_messages, self.next_recv_index - len(expected_messages)
                ):
                    self.cumulative_waits += 0.1

                    if self.cumulative_waits > 1.0:
                        self.replay_failure = True
                        message_loop.stop()
                        return False

                    self.timer.start(0.1)
                    break

                if next_recv_event.topic in self.subscriptions:
                    self.recorded_events.add(
                        MessageEvent(
                            MessageEventKind.RECV,
                            t,
                            next_recv_event.topic,
                            next_recv_event.payload,
                        )
                    )
                    self.on_message(next_recv_event.topic, next_recv_event.payload)

                assert self.next_recv_index is not None
                self.next_recv_index = self.playback_events.get_next_recv_index(
                    self.next_recv_index
                )
            else:
                self.timer.start(next_recv_event.time - t + 0.1)
                break

        return True

    @override
    def loop_forever(self):
        self.on_connect(100)

        if self.prepare_next_callback():
            message_loop.run()
