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

import time
from typing import final, override, Dict, Any

from emkyoot.parameters import Broadcaster

from .message_loop import AsyncUpdater
from .mqtt_client import MqttClient, MqttSubscriber
from .parameters import (
    NumericParameter,
    QueryableNumericParameter,
    SettableAndQueryableNumericParameter,
    SettableAndQueryableToggleParameter,
)


class Device(MqttSubscriber, AsyncUpdater):
    def __init__(self, property_name: str):
        MqttSubscriber.__init__(self, property_name)
        self._numeric_parameters: Dict[str, NumericParameter] = {}
        self._register_parameter_members()

    @override
    def _on_message(self, payload: Dict[Any, Any]):
        for k, v in payload.items():
            if k in self._numeric_parameters.keys():
                self._numeric_parameters[k]._set_reported_value(v)

    @final
    def _query_queryable_parameters(self):
        for _, param in vars(self).items():
            if isinstance(param, QueryableNumericParameter):
                param.query_device()

    # ==========================================================================
    # @internal
    @final
    def _register_parameter_members(self):
        for key, member in vars(self).items():
            if isinstance(member, NumericParameter):
                self._numeric_parameters[member.get_property_name()] = member
                member._wants_to_call_listeners_broadcaster.add_listener(
                    self._parameter_changed
                )
                member._wants_to_query_device_boradcaster.add_listener(
                    self._parameter_changed
                )

    # @internal
    @override
    def _handle_async_update(self):
        for k, param in self._numeric_parameters.items():
            param._call_listeners_if_necessary()

        if not self.is_connected():
            time.sleep(0.1)
            self._trigger_async_update()
            return

        self._publish_changes()
        self._query_parameters()

    # @internal
    @final
    def _parameter_changed(self) -> None:
        self._trigger_async_update()

    # @internal
    def _publish_changes(self):
        mqtt_update: Dict[str, Any] = {}

        for k, param in self._numeric_parameters.items():
            param._append_dictionary_sent_to_device(mqtt_update)

        if mqtt_update:
            self.publish(mqtt_update)

    # @internal
    def _query_parameters(self):
        mqtt_query: Dict[str, Any] = {}

        for k, param in self._numeric_parameters.items():
            if param._should_device_be_queryied():
                mqtt_query[param.get_property_name()] = ""

        if mqtt_query:
            self.query(mqtt_query)


class DimmableLight:
    def __init__(self, brightness_min: float, brightness_max: float):
        self.brightness = SettableAndQueryableNumericParameter(
            "brightness", brightness_min, brightness_max
        )
        self.state = SettableAndQueryableToggleParameter("state")


class DevicesClient(MqttClient):
    def __init__(self, no_query: bool = False):
        super().__init__()
        self._no_query = no_query
        self.on_connect = Broadcaster()

    @override
    def _on_connect_message_thread(
        self, client, userdata, flags, reason_code, properties
    ):
        super()._on_connect_message_thread(
            client, userdata, flags, reason_code, properties
        )

        if not self._no_query:
            for key, device in vars(self).items():
                if not isinstance(device, Device):
                    continue

                device._query_queryable_parameters()

        self.on_connect._call_listeners()

    @override
    def _on_message_message_thread(self, client, userdata, msg):
        super()._on_message_message_thread(client, userdata, msg)
