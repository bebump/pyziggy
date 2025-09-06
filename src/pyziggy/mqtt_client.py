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

from __future__ import annotations

import json
import logging
from abc import abstractmethod
from pathlib import Path
from ssl import SSLCertVerificationError
from typing import Dict, Any, final, Optional, override

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


class MqttClientImpl:
    @abstractmethod
    def connect(
        self,
        host: str,
        port: int,
        keepalive: int,
        username: str | None = None,
        password: str | None = None,
        ca_crt: Path | None = None,
        client_crt: Path | None = None,
        client_key: Path | None = None,
        check_server_crt: bool = False,
    ):
        pass

    @abstractmethod
    def was_on_connect_called(self) -> bool:
        pass

    @abstractmethod
    def set_on_connect(self, callback):
        pass

    @abstractmethod
    def set_on_message(self, callback):
        pass

    @abstractmethod
    def subscribe(self, topic: str):
        pass

    @abstractmethod
    def publish(self, topic: str, payload: Dict[str, Any]):
        pass

    @abstractmethod
    def loop_forever(self) -> int:
        pass


class PahoMqttClientImpl(MqttClientImpl):
    def __init__(self):
        self._mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._mqttc.on_connect = self._on_connect
        self._mqttc.on_message = self._on_message
        self._on_connect_callback = None
        self._on_message_callback = None
        self._on_connect_was_called = False

    @override
    def connect(
        self,
        host: str,
        port: int,
        keepalive: int,
        username: str | None = None,
        password: str | None = None,
        ca_crt: Path | None = None,
        client_crt: Path | None = None,
        client_key: Path | None = None,
        check_server_crt: bool = False,
    ):
        use_tls = ca_crt is not None or client_crt is not None or client_key is not None

        if use_tls:
            args = {}

            if ca_crt is not None:
                args["ca_certs"] = str(ca_crt)

            if client_crt is not None:
                args["certfile"] = str(client_crt)

            if client_key is not None:
                args["keyfile"] = str(client_key)

            self._mqttc.tls_set(**args)  # type: ignore
            self._mqttc.tls_insecure_set(not check_server_crt)

            if not check_server_crt:
                print(
                    "[WARNING] Using SSL/TLS with disabled server certificate validation."
                    " The identity of the server cannot be verified. See the"
                    ' "check_server_crt" option in the configuration file.'
                )

        if username is not None:
            self._mqttc.username_pw_set(username, password)

        try:
            self._mqttc.connect(host, port, keepalive)
            return
        except TimeoutError as e:
            print(
                f"[ERROR] The MQTT server connection attempt timed out. Exception message: {e}"
            )
        except ConnectionRefusedError as e:
            print(
                f"[ERROR] Failed to connect to MQTT server with connection refused error: {e}"
            )
        except SSLCertVerificationError as e:
            print(
                f"[ERROR] The MQTT server failed the certificate check against"
                f' "{ca_crt}". The identity of the MQTT server cannot be'
                f" verified. Exception message: {e}"
            )
        except OSError as e:
            print(
                f"[ERROR] The MQTT server connection attempt failed. Exception message: {e}"
            )

        exit(1)

    @override
    def was_on_connect_called(self) -> bool:
        return self._on_connect_was_called

    @override
    def loop_forever(self) -> int:
        self._mqttc.loop_start()
        return_code = message_loop.run()
        self._mqttc.disconnect()
        return return_code

    @override
    def publish(self, topic: str, payload: Dict[str, Any]):
        self._mqttc.publish(
            topic,
            json.dumps(payload),
            qos=1,
        )

    @override
    def subscribe(self, topic: str):
        self._mqttc.subscribe(topic)

    @override
    def set_on_connect(self, callback):
        self._on_connect_callback = callback

    @override
    def set_on_message(self, callback):
        self._on_message_callback = callback

    # ==========================================================================
    def _on_connect(self, client, userdata, flags, reason_code, properties):
        def callback():
            self._on_connect_message_thread(
                client, userdata, flags, reason_code, properties
            )

        message_loop.post_message(callback)

        if reason_code.value == 0:
            self._on_connect_was_called = True
            return

        print(f"[ERROR] MQTT connection failure: {reason_code}")
        message_loop.stop(1)

    def _on_message(self, client, userdata, msg):
        def callback():
            self._on_message_message_thread(client, userdata, msg)

        message_loop.post_message(callback)

    def _on_connect_message_thread(
        self, client, userdata, flags, reason_code, properties
    ):
        if self._on_connect_callback is None:
            return

        self._on_connect_callback(reason_code)

    def _on_message_message_thread(self, client, userdata, msg):
        if self._on_message_callback is None:
            return

        self._on_message_callback(msg.topic, json.loads(msg.payload))


class MqttClient:
    def __init__(self, impl: MqttClientImpl | None = None):
        self._base_topic: str = ""
        self._dispatch: Dict[str, MqttSubscriber] = {}
        self._impl: MqttClientImpl = impl if impl is not None else PahoMqttClientImpl()

        self._impl.set_on_connect(self._on_connect)
        self._impl.set_on_message(self._on_message)

    @final
    def _connect(
        self,
        host: str,
        port: int,
        keepalive: int,
        base_topic: str,
        username: str | None = None,
        password: str | None = None,
        ca_crt: Path | None = None,
        client_crt: Path | None = None,
        client_key: Path | None = None,
        check_server_crt: bool = False,
    ):
        self._base_topic = base_topic
        self._impl.connect(
            host,
            port,
            keepalive,
            username,
            password,
            ca_crt,
            client_crt,
            client_key,
            check_server_crt,
        )

    @final
    def _loop_forever(self) -> int:
        """
        Starts the message loop. This function only returns after the message loop has been terminated.

        To terminate the message loop call

        from pyziggy.message_loop import message_loop
        message_loop.stop()
        """
        return self._impl.loop_forever()

    def _on_connect(self, reason_code):
        for key, member in vars(self).items():
            if not isinstance(member, MqttSubscriber):
                continue

            topic = f"{self._base_topic}/{member._get_topic()}"
            self._dispatch[topic] = member
            self._impl.subscribe(topic)
            member._on_connect(MqttClientPublisher(self, topic))

    def _on_message(self, topic: str, payload: Dict[str, Any]):
        logger.debug(f'RECEIVE "{topic}"\n{payload}')

        if topic in self._dispatch.keys():
            logger.debug(f"DISPATCH to {topic} handler\n")
            self._dispatch[topic]._on_message(payload)

    # ==========================================================================
    @final
    def _publish(self, topic: str, payload: Dict[str, Any]):
        logger.debug(f'PUBLISH on "{topic}"\n{payload}\n')
        self._impl.publish(topic, payload)
