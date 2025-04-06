# emkyoot - Run automation scripts that interact with zigbee2mqtt.
# Copyright (C) 2025  Attila Szarvas
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

from __future__ import annotations

import json
import logging
from typing import Dict, Any, final, Optional

import paho.mqtt.client as mqtt

from .message_loop import message_loop

logger = logging.getLogger(__name__)


class MqttSubscriber:
    def __init__(self, topic):
        self._topic = topic
        self._publisher: Optional[MqttClientPublisher] = None

    def publish(self, payload: Dict[str, Any]):
        if self._publisher is not None:
            self._publisher.publish(payload)
        else:
            raise RuntimeError("An error occurred")

    def query(self, properties: Dict[str, str]):
        if self._publisher is not None:
            self._publisher.query(properties)
        else:
            raise RuntimeError("An error occurred")

    def is_connected(self):
        return self._publisher is not None

    @final
    def _get_topic(self) -> str:
        return self._topic

    def _on_message(self, payload: Dict[Any, Any]) -> None:
        """This function is called on the message thread."""
        pass

    def _on_connect(self, publisher: MqttClientPublisher) -> None:
        """This function is called on the message thread."""
        self._publisher = publisher


class MqttClientPublisher:
    def __init__(self, client: MqttClient, topic: str):
        self._client = client
        self._topic = topic

    def publish(self, payload: Dict[str, Any]):
        self._client._publish(self._topic + "/set", payload)

    def query(self, properties: Dict[str, str]):
        self._client._publish(self._topic + "/get", properties)


class MqttClient:
    def __init__(self):
        self._dispatch: Dict[str, MqttSubscriber] = {}
        self._mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._mqttc.on_connect = self._on_connect
        self._mqttc.on_message = self._on_message
        self._should_disconnect = False
        self._base_topic: str = ""

    @final
    def connect(self, host, port, keepalive, base_topic: str):
        self._base_topic = base_topic
        self._mqttc.connect(host, port, keepalive)

    @final
    def disconnect(self):
        self._should_disconnect = True

    @final
    def loop_forever(self):
        self._mqttc.loop_start()
        message_loop.run()
        self._mqttc.disconnect()

    # ==========================================================================
    def _on_connect_message_thread(
        self, client, userdata, flags, reason_code, properties
    ):
        for key, member in vars(self).items():
            if not isinstance(member, MqttSubscriber):
                continue

            topic = f"{self._base_topic}/{member._get_topic()}"
            self._dispatch[topic] = member
            client.subscribe(topic)
            member._on_connect(MqttClientPublisher(self, topic))

    def _on_message_message_thread(self, client, userdata, msg):
        logger.debug(f'RECEIVE "{msg.topic}"\n{json.loads(msg.payload)}')

        if msg.topic in self._dispatch.keys():
            logger.debug(f'DISPATCH to {msg.topic} handler\n')
            self._dispatch[msg.topic]._on_message(json.loads(msg.payload))

    # ==========================================================================
    @final
    def _publish(self, topic: str, payload: Dict[str, Any]):
        logger.debug(f'PUBLISH on "{topic}"\n{payload}\n')

        self._mqttc.publish(
            topic,
            json.dumps(payload),
            qos=1,
        )

    @final
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        def callback():
            self._on_connect_message_thread(
                client, userdata, flags, reason_code, properties
            )

        message_loop.post_message(callback)

    @final
    def _on_message(self, client, userdata, msg):
        def callback():
            self._on_message_message_thread(client, userdata, msg)

        message_loop.post_message(callback)
