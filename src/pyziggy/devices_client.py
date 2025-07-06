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

import logging
import time
from typing import final, override, Dict, Any, List

from pyziggy.parameters import Broadcaster
from .message_loop import AsyncUpdater
from .mqtt_client import MqttClient, MqttSubscriber, MqttClientImpl
from .parameters import (
    ParameterBase,
    QueryableNumericParameter,
)

logger = logging.getLogger(__name__)


class Device(MqttSubscriber, AsyncUpdater):
    def __init__(self, property_name: str):
        MqttSubscriber.__init__(self, property_name)
        self._parameters: Dict[str, List[ParameterBase]] = {}
        self._register_parameter_members()
        self._sync_parameters_requesting_callback: List[ParameterBase] = []
        self._in_on_message = False

    @final
    def get_parameters(self) -> List[ParameterBase]:
        params: List[ParameterBase] = []

        for k, ps in self._parameters.items():
            params += ps

        return params

    @override
    def _on_message(self, payload: Dict[Any, Any]):
        self._in_on_message = True

        for k, v in payload.items():
            if k in self._parameters.keys():
                for p in self._parameters[k]:
                    if v is None:
                        # Sometimes a null value is sent by z2m. For example the
                        # "identify" enum property, which only has a single value
                        # "identify", will receive an update, where the value is
                        # null (translated to None at this point).
                        pass
                    else:
                        p._set_reported_value(v)

        self._in_on_message = False
        self._execute_synchronous_parameter_callbacks()

    def _execute_synchronous_parameter_callbacks(self):
        for param in self._sync_parameters_requesting_callback:
            param._call_listeners()

        self._sync_parameters_requesting_callback.clear()

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
            if isinstance(member, ParameterBase):
                if member.get_property_name() not in self._parameters:
                    self._parameters[member.get_property_name()] = []

                self._parameters[member.get_property_name()] += [member]

                member._wants_to_call_listeners_broadcaster.add_listener(
                    self._parameter_changed
                )
                member._wants_to_query_device_boradcaster.add_listener(
                    self._parameter_changed
                )
                member._wants_to_call_listeners_synchronously_broadcaster.add_listener(
                    self._synchronous_parameter_changed
                )

    # @internal
    @override
    def _handle_async_update(self):
        for param in self.get_parameters():
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
    @final
    def _synchronous_parameter_changed(self, parameter: ParameterBase) -> None:
        self._sync_parameters_requesting_callback.append(parameter)

        if not self._in_on_message:
            self._execute_synchronous_parameter_callbacks()

    # @internal
    def _publish_changes(self):
        mqtt_update: Dict[str, Any] = {}

        for param in self.get_parameters():
            param._append_dictionary_sent_to_device(mqtt_update)

        if mqtt_update:
            self.publish(mqtt_update)

    # @internal
    def _query_parameters(self):
        mqtt_query: Dict[str, Any] = {}

        for param in self.get_parameters():
            if param._should_device_be_queryied():
                mqtt_query[param.get_property_name()] = ""

        if mqtt_query:
            self.query(mqtt_query)


class DevicesClient(MqttClient):
    """
    A class that acts as a collection of devices, which also takes care of the
    communication between these device objects and an MQTT server.

    Attributes
    ----------
    on_connect : Broadcaster
        Use add_listener on this Broadcaster object if you'd like to receive
        a callback when a successful connection is established to the MQTT
        server.

    Methods
    -------
    get_devices():
        Returns all Device members of the DevicesClient object. This can be a
        handy way to iterate over all your devices.
    """

    def __init__(self, impl: MqttClientImpl | None = None):
        super().__init__(impl)
        self._skip_initial_query: bool = False
        self.on_connect: Broadcaster = Broadcaster()

    @final
    def get_devices(self) -> List[Device]:
        """
        Returns all Device members of the DevicesClient object. This can be a
        handy way to iterate over all your devices.
        """
        devices = []

        for key, device in vars(self).items():
            if isinstance(device, Device):
                devices.append(device)

        return devices

    def _set_skip_initial_query(self, skip: bool) -> None:
        """
        By default, a DevicesClient will send a query message upon startup to the MQTT server for all
        device parameters. This ensures that all parameters will reflect the actual device states as
        soon as possible, but it also generates a lot of traffic on startup, which may make tests harder
        to follow and short scripts (just turning on a light) unnecessarily communication heavy.

        Calling this function with `True` suppresses this initial querying behavior.
        """
        self._skip_initial_query = skip

    @override
    def _on_connect(self, reason_code):
        super()._on_connect(reason_code)

        if not self._skip_initial_query:
            for key, device in vars(self).items():
                if not isinstance(device, Device):
                    continue

                device._query_queryable_parameters()

        self.on_connect._call_listeners()

    @override
    def _on_message(self, topic: str, payload: Dict[str, Any]):
        super()._on_message(topic, payload)
