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
from abc import abstractmethod
from enum import Enum
from typing import Dict, Union, List, Any, final, override
from typing import Type, TypeVar

from .broadcasters import Broadcaster, AnyBroadcaster

logger = logging.getLogger(__name__)


class ParameterBase(Broadcaster):
    def __init__(self, property: str):
        super().__init__()
        self._property: str = property
        self._wants_to_call_listeners_broadcaster = Broadcaster()
        self._wants_to_call_listeners_synchronously_broadcaster = AnyBroadcaster()
        self._wants_to_query_device_boradcaster = Broadcaster()
        self._should_call_listeners = False

        # Setting this to True is only allowed for gettable devices.
        # See zigbee2mqtt access property
        self._should_query_device: bool = False

        # Setting this to True is only allowed for settable devices.
        # See zigbee2mqtt access property
        self._should_send_to_device: bool = False

        self._use_synchronous_callbacks: bool = False

    @final
    def _query_device(self):
        self._should_query_device = True
        self._wants_to_query_device_boradcaster._call_listeners()

    @final
    def get_property_name(self):
        return self._property

    @abstractmethod
    def _set_reported_value(self, value: Any) -> None:
        pass

    @abstractmethod
    def _append_dictionary_sent_to_device(
        self, out_dict: Dict[str, Union[bool, int, str]]
    ) -> None:
        pass

    @abstractmethod
    def _should_device_be_queryied(self) -> bool:
        pass

    @abstractmethod
    def _call_listeners_if_necessary(self):
        pass


class NumericParameter(ParameterBase):
    def __init__(self, property: str, min_value: float, max_value: float):
        super().__init__(property)
        self._report_delay_tolerance: float = 1.0
        self._requested_value: float = 0
        self._requested_timestamp: float = 0
        self._reported_value: float = 0
        self._reported_timestamp: float = 0
        self._min_value: float = min_value
        self._max_value: float = max_value

    def set_use_synchronous_broadcast(self, value: bool):
        self._use_synchronous_callbacks = value

    def _reported_value_is_probably_up_to_date(self):
        if self._should_send_to_device:
            return False

        if self._reported_timestamp == 0:
            return False

        if self._reported_timestamp - self._requested_timestamp > 0.2:
            return True

        if time.perf_counter() - self._reported_timestamp > 1.0:
            return True

        return False

    @final
    def get(self) -> float:
        if self._reported_value_is_probably_up_to_date():
            return self._reported_value

        return self._requested_value

    @final
    def get_normalized(self) -> float:
        return (self.get() - self._min_value) / (self._max_value - self._min_value)

    @final
    @override
    def _set_reported_value(self, value: Any) -> None:
        old_value = self.get()
        new_value = self._transform_mqtt_to_internal_value(value)
        old_reported_timestamp = self._reported_timestamp
        new_reported_timestamp = time.perf_counter()

        if old_value != new_value:
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
    @override
    def _append_dictionary_sent_to_device(
        self, out_dict: Dict[str, Union[bool, int, str]]
    ) -> None:
        if not self._should_send_to_device:
            return

        out_dict[self._property] = self._transform_internal_to_mqtt_value(self.get())
        self._should_send_to_device = False

    @final
    @override
    def _should_device_be_queryied(self) -> bool:
        if self._should_query_device:
            self._should_query_device = False
            return True

        return False

    @final
    @override
    def _call_listeners_if_necessary(self):
        if self._should_call_listeners:
            self._should_call_listeners = False
            self._call_listeners()

    def _transform_internal_to_mqtt_value(self, value: float) -> Any:
        return value

    def _transform_mqtt_to_internal_value(self, value: Any) -> float:
        return value


class SettableNumericParameter(NumericParameter):
    def __init__(self, property: str, min_value: float, max_value: float):
        super().__init__(property, min_value, max_value)
        self._stale = True

    def mark_as_stale(self):
        """
        Mark the parameter as stale. This is used to force an update to the
        device when the parameter is set, even if the value has not changed.
        """
        self._stale = True

    def set(self, value: float) -> None:
        value = min(self._max_value, max(self._min_value, value))

        if value != self.get() or self._stale:
            self._requested_value = min(self._max_value, max(self._min_value, value))
            self._requested_timestamp = time.perf_counter()
            self._should_send_to_device = True
            self._should_call_listeners = True

            if self._use_synchronous_callbacks:
                self._wants_to_call_listeners_synchronously_broadcaster._call_listeners(
                    lambda listener: listener(self)
                )
            else:
                self._wants_to_call_listeners_broadcaster._call_listeners()

        self._stale = False

    def set_normalized(self, value: float) -> None:
        self.set(
            float(round(value * (self._max_value - self._min_value) + self._min_value))
        )

    def add(self, value: float) -> None:
        self.set(self.get() + value)

    def add_normalized(self, value: float) -> None:
        self.set_normalized(self.get_normalized() + value)


class QueryableNumericParameter(NumericParameter):
    def query_device(self) -> None:
        self._query_device()


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


class CompositeParameter(ParameterBase):
    def __init__(self, property: str):
        super().__init__(property)
        self._parameters: Dict[str, ParameterBase] = {}

        self._hook_into_subparameters()

    def _hook_into_subparameters(self):
        for param in self._get_subparameters():
            self._parameters[param.get_property_name()] = param

            param._wants_to_call_listeners_broadcaster.add_listener(
                lambda: self._wants_to_call_listeners_broadcaster._call_listeners()
            )
            param._wants_to_query_device_boradcaster.add_listener(
                lambda: self._wants_to_query_device_boradcaster._call_listeners()
            )
            param._wants_to_call_listeners_synchronously_broadcaster.add_listener(
                lambda _: self._wants_to_call_listeners_synchronously_broadcaster._call_listeners(
                    lambda callback: callback(self)
                )
            )

    def _get_subparameters(self):
        return [
            param for _, param in vars(self).items() if isinstance(param, ParameterBase)
        ]

    @final
    def mark_as_stale(self):
        """
        Mark the parameter as stale. This is used to force an update to the
        device when the parameter is set, even if the value has not changed.
        """
        for param in self._get_subparameters():
            if isinstance(param, SettableNumericParameter):
                param.mark_as_stale()

    @final
    @override
    def _call_listeners_if_necessary(self):
        for param in self._get_subparameters():
            param._call_listeners_if_necessary()

    @final
    @override
    def _append_dictionary_sent_to_device(self, out_dict) -> None:
        sub_dict: Dict[str, Any] = {}

        for param in self._get_subparameters():
            param._append_dictionary_sent_to_device(sub_dict)

        if sub_dict:
            out_dict[self._property] = sub_dict

    @final
    @override
    def _set_reported_value(self, value: Any) -> None:
        if not isinstance(value, Dict):
            logger.warning(
                f"{self.get_property_name()} received {value}. I didn't think this was possible."
            )
            return

        for k, v in value.items():
            if k in self._parameters:
                self._parameters[k]._set_reported_value(v)

    @final
    @override
    def _should_device_be_queryied(self) -> bool:
        should_device_be_queryied = self._should_query_device
        self._should_query_device = False

        for param in self._get_subparameters():
            should_device_be_queryied = (
                should_device_be_queryied or param._should_device_be_queryied()
            )

        return should_device_be_queryied
