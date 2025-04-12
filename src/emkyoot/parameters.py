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
from enum import Enum
from typing import Dict, Union, List, Any, final, Callable
from typing import Type, TypeVar


class ListenerCancellationToken:
    def __init__(self, broadcaster, listener_id: int):
        self._broadcaster = broadcaster
        self._listener_id = listener_id

    def stop_listening(self):
        self._broadcaster._remove_listener(self._listener_id)


class Broadcaster:
    def __init__(self):
        self._listeners: Dict[int, Callable[[], None]] = {}

    def add_listener(self, callback: Callable[[], None]) -> ListenerCancellationToken:
        listener_id = len(self._listeners)
        self._listeners[listener_id] = callback
        return ListenerCancellationToken(self, listener_id)

    def _call_listeners(self):
        for k, listener in self._listeners.items():
            listener()

    def _remove_listener(self, listener_id: int) -> None:
        del self._listeners[listener_id]


class AnyBroadcaster:
    def __init__(self):
        self._listeners: Dict[int, Any] = {}

    def add_listener(self, callback: Any) -> ListenerCancellationToken:
        listener_id = len(self._listeners)
        self._listeners[listener_id] = callback
        return ListenerCancellationToken(self, listener_id)

    def _call_listeners(self, callback: Callable[[Any], None]):
        for k, listener in self._listeners.items():
            callback(listener)

    def _remove_listener(self, listener_id: int) -> None:
        del self._listeners[listener_id]


class NumericParameter(Broadcaster):
    def __init__(self, property: str, min_value: float, max_value: float):
        super().__init__()
        self._report_delay_tolerance: float = 1.0
        self._property = property
        self._requested_value: float = 0
        self._requested_timestamp: float = 0
        self._reported_value: float = 0
        self._reported_timestamp: float = 0
        self._min_value: float = min_value
        self._max_value: float = max_value
        self._should_call_listeners = False
        self._wants_to_call_listeners_broadcaster = Broadcaster()
        self._wants_to_call_listeners_synchronously_broadcaster = AnyBroadcaster()
        self._wants_to_query_device_boradcaster = Broadcaster()

        # Setting this to True is only allowed for gettable devices.
        # See zigbee2mqtt access property
        self._should_query_device: bool = False

        # Setting this to True is only allowed for settable devices.
        # See zigbee2mqtt access property
        self._should_send_to_device: bool = False

        self._use_synchronous_callbacks: bool = False

    def set_use_synchronous_broadcast(self, value: bool):
        self._use_synchronous_callbacks = value

    def _reported_value_is_probably_up_to_date(self):
        if self._should_send_to_device:
            return False

        return (
            self._reported_timestamp - self._requested_timestamp
            > self._report_delay_tolerance
        )

    @final
    def get(self) -> float:
        if self._reported_value_is_probably_up_to_date():
            return self._reported_value

        return self._requested_value

    @final
    def get_normalised(self) -> float:
        return (self.get() - self._min_value) / (self._max_value - self._min_value)

    @final
    def get_property_name(self):
        return self._property

    @final
    def _set_reported_value(self, value: Any) -> None:
        old_value = self.get()
        new_value = self._transform_mqtt_to_internal_value(value)
        old_reported_timestamp = self._reported_timestamp
        new_reported_timestamp = time.perf_counter()

        if old_value != new_value or (
            self._reported_value_is_probably_up_to_date()
            and new_reported_timestamp > old_reported_timestamp
        ):
            if self._use_synchronous_callbacks:
                self._wants_to_call_listeners_synchronously_broadcaster._call_listeners(
                    lambda callback: callback(self)
                )
            else:
                self._should_call_listeners = True
                self._wants_to_call_listeners_broadcaster._call_listeners()

        self._reported_value = new_value
        self._reported_timestamp = new_reported_timestamp

    @final
    def _append_dictionary_sent_to_device(
        self, out_dict: Dict[str, Union[bool, int, str]]
    ) -> None:
        if not self._should_send_to_device:
            return

        out_dict[self._property] = self._transform_internal_to_mqtt_value(self.get())
        self._should_send_to_device = False

    @final
    def _should_device_be_queryied(self) -> bool:
        if self._should_query_device:
            self._should_query_device = False
            return True

        return False

    def _transform_internal_to_mqtt_value(self, value: float) -> Any:
        return value

    def _transform_mqtt_to_internal_value(self, value: Any) -> float:
        return value

    def _call_listeners_if_necessary(self):
        if self._should_call_listeners:
            self._should_call_listeners = False
            self._call_listeners()


class SettableNumericParameter(NumericParameter):
    def set(self, value: float) -> None:
        value = min(self._max_value, max(self._min_value, value))

        if value != self.get():
            self._requested_value = min(self._max_value, max(self._min_value, value))
            self._requested_timestamp = time.perf_counter()
            self._should_send_to_device = True
            self._should_call_listeners = True

            if self._use_synchronous_callbacks:
                self._wants_to_call_listeners_synchronously_broadcaster._call_listeners(
                    self
                )
            else:
                self._wants_to_call_listeners_broadcaster._call_listeners()

    def set_normalised(self, value: float) -> None:
        self.set(
            float(round(value * (self._max_value - self._min_value) + self._min_value))
        )

    def add(self, value: float) -> None:
        self.set(self.get() + value)

    def add_normalised(self, value: float) -> None:
        self.set_normalised(self.get_normalised() + value)


class QueryableNumericParameter(NumericParameter):
    def query_device(self) -> None:
        self._should_query_device = True
        self._wants_to_query_device_boradcaster._call_listeners()


class SettableAndQueryableNumericParameter(
    QueryableNumericParameter, SettableNumericParameter
):
    pass


class BinaryParameter(NumericParameter):
    def __init__(self, property: str):
        super().__init__(property, 0, 1)

    def _transform_internal_to_mqtt_value(self, value: float) -> Any:
        return True if value == 1 else False

    def _transform_mqtt_to_internal_value(self, value: Any) -> float:
        return 1 if value == True else 0


class QueryableBinaryParameter(BinaryParameter, QueryableNumericParameter):
    pass


class SettableBinaryParameter(BinaryParameter, SettableNumericParameter):
    pass


class SettableAndQueryableBinaryParameter(
    BinaryParameter, SettableAndQueryableNumericParameter
):
    pass


class ToggleParameter(NumericParameter):
    def __init__(self, property: str):
        super().__init__(property, 0, 1)

    def _transform_internal_to_mqtt_value(self, value: float) -> Any:
        return "ON" if value == 1 else "OFF"

    def _transform_mqtt_to_internal_value(self, value: Any) -> float:
        return 1 if value == "ON" else 0


class QueryableToggleParameter(ToggleParameter, QueryableNumericParameter):
    pass


class SettableToggleParameter(ToggleParameter, SettableNumericParameter):
    pass


class SettableAndQueryableToggleParameter(
    ToggleParameter, SettableAndQueryableNumericParameter
):
    pass


class EnumParameter(NumericParameter):
    def __init__(self, property: str, enum_values: List[str]):
        super().__init__(property, 0, len(enum_values))
        self._enum_values = enum_values

    def _transform_internal_to_mqtt_value(self, value: float) -> Any:
        return self._enum_values[int(value)]

    def _transform_mqtt_to_internal_value(self, value: Any) -> float:
        for i in range(0, len(self._enum_values)):
            if self._enum_values[i] == value:
                return i

        return 0


class SettableEnumParameter(EnumParameter, SettableNumericParameter):
    pass


T = TypeVar("T", bound=Enum)


def int_to_enum(enum_type: Type[T], index: int) -> T:
    return list(enum_type)[index]
