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

import os
from pathlib import Path
from typing import List, Dict, Any, override

from .device_definition_parser import (
    NumericParameterDefinition,
    DeviceDefinition,
    EnumParameterDefinition,
    ParameterBaseDefinition,
    ToggleParameterDefinition,
)
from .message_loop import message_loop
from .mqtt_client import MqttClient, MqttSubscriber


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


class StrEnumValuesStorage:
    def __init__(self, enum_values: List[str]):
        self.enum_values = enum_values.copy()
        self.enum_values.sort()

    def __hash__(self) -> int:
        return hash("".join(self.enum_values))

    def __eq__(self, other) -> bool:
        return self.enum_values == other.enum_values


class EnumClassGenerator:
    def __init__(self):
        self.enum_name_for_enum_values_storage: Dict[StrEnumValuesStorage, str] = {}

    def get_enum_class_name(self, enum_values: List[str]):
        enum_values_storage = StrEnumValuesStorage(enum_values)

        if enum_values_storage not in self.enum_name_for_enum_values_storage.keys():
            self.enum_name_for_enum_values_storage[enum_values_storage] = (
                f"Enum{len(self.enum_name_for_enum_values_storage)}"
            )

        return self.enum_name_for_enum_values_storage[enum_values_storage]

    def get_code_for_enum_class_definitions(self):
        code = ""

        if self.enum_name_for_enum_values_storage:
            code += f"from enum import Enum\n\n"

        for (
            enum_values_storage,
            enum_name,
        ) in self.enum_name_for_enum_values_storage.items():
            code += f"class {enum_name}(Enum):\n"

            for value in enum_values_storage.enum_values:
                code += f'    {value.replace("/", "_")} = "{value}"\n'

            code += "\n"

        return code


class ClassStuff:
    def __init__(self):
        self.names: set[str] = set()
        self.name_for_code: Dict[str, str] = {}

    def get_class_name(self, code, name_base: str):
        if code not in self.name_for_code.keys():
            name = name_base

            i = 1
            while True:
                if name not in self.names:
                    break

                name = name_base + f"Variant{i}"
                i += 1

            self.name_for_code[code] = name
            self.names.add(name)

        return self.name_for_code[code]

    def get_class_code(self, name_in: str) -> str:
        for code, name in self.name_for_code.items():
            if name == name_in:
                return code.replace("$class_name", name)

        return ""

    def get_class_names_in_order(self):
        ordered_names = [n for n in self.names]
        ordered_names.sort()
        return ordered_names


class StuffStuff:
    def __init__(self):
        self.enum_names_for_not_settable = set()
        self.enum_names_for_settable = set()

    def get_typename_for_settable_parameter_for(self, enum_name: str) -> str:
        self.enum_names_for_not_settable.add(enum_name)
        self.enum_names_for_settable.add(enum_name)
        return f"SettableEnumParameterFor{enum_name}"

    def get_typename_for_parameter_for(self, enum_name: str) -> str:
        self.enum_names_for_not_settable.add(enum_name)
        return f"EnumParameterFor{enum_name}"

    def get_code_for_enum_parameter_definitions(self):
        code = ""

        enums = list(self.enum_names_for_not_settable)
        enums.sort()

        for enum in enums:
            code += (
                f"class {self.get_typename_for_parameter_for(enum)}(EnumParameter):\n"
            )
            code += f"    def __init__(self, property: str, enum_values: List[str]):\n"
            code += f"        super().__init__(property, enum_values)\n"
            code += f"        self.enum_type = {enum}\n\n"

            code += f"    def get_enum_value(self) -> {enum}:\n"
            code += f"        return int_to_enum({enum}, self.get())" "\n\n"

        settable_enums = list(self.enum_names_for_settable)
        settable_enums.sort()

        for enum in settable_enums:
            code += f"class {self.get_typename_for_settable_parameter_for(enum)}(SettableEnumParameter, {self.get_typename_for_parameter_for(enum)}):\n"
            code += f"    def set_enum_value(self, value: {enum}) -> None:\n"
            code += f"        self.set(self._transform_mqtt_to_internal_value(value.value))\n\n"

        return code


enum_stuff = EnumClassGenerator()
class_stuff = ClassStuff()
stuff_stuff = StuffStuff()


def generate_parameter_member(parameter: ParameterBaseDefinition):
    if isinstance(parameter, EnumParameterDefinition):
        access_type = parameter.access_type
        enum_name = enum_stuff.get_enum_class_name(parameter.enum_definition.values)

        if access_type.is_settable():
            return f"""        self.{parameter.property} = {stuff_stuff.get_typename_for_settable_parameter_for(enum_name)}("{parameter.property}", [e.value for e in {enum_name}])"""

        return f"""        self.{parameter.property} = {stuff_stuff.get_typename_for_parameter_for(enum_name)}("{parameter.property}", [e.value for e in {enum_name}])"""

    if isinstance(parameter, ToggleParameterDefinition):
        access_type = parameter.access_type

        if access_type.is_settable():
            if access_type.is_queryable():
                return f"""        self.{parameter.property} = SettableAndQueryableToggleParameter("{parameter.property}")"""
            else:
                return f"""        self.{parameter.property} = SettableToggleParameter("{parameter.property}")"""
        else:
            if access_type.is_queryable():
                return f"""        self.{parameter.property} = QueryableToggleParameter("{parameter.property}")"""

        return f"""        self.{parameter.property} = ToggleParameter("{parameter.property}")"""

    if isinstance(parameter, NumericParameterDefinition):
        access_type = parameter.access_type

        if access_type.is_settable():
            if access_type.is_queryable():
                return f"""        self.{parameter.property} = SettableAndQueryableNumericParameter("{parameter.property}", {parameter.value_min}, {parameter.value_max})"""
            else:
                return f"""        self.{parameter.property} = SettableNumericParameter("{parameter.property}", {parameter.value_min}, {parameter.value_max})"""
        else:
            if access_type.is_queryable():
                return f"""        self.{parameter.property} = QueryableNumericParameter("{parameter.property}", {parameter.value_min}, {parameter.value_max})"""

        return f"""        self.{parameter.property} = NumericParameter("{parameter.property}", {parameter.value_min}, {parameter.value_max})"""


def get_device_class_name_base(device: DeviceDefinition) -> str:
    if device.vendor == "Philips" and device.model_id == "RDM002":
        return "PhilipsTapDialSwitch"

    for param in device.parameters:
        if param.property == "brightness":
            return "Light"

    return f"{sanitise_type_name(device.vendor)}_{sanitise_type_name(device.model_id)}"


def generate_device(device: DeviceDefinition):
    member_entries = []

    for parameter in device.parameters:
        p = generate_parameter_member(parameter)

        if p is not None:
            member_entries.append(p)

    class_name = get_device_class_name_base(device)

    device_template = """class $class_name(Device):
    def __init__(self, name):
"""

    if member_entries:
        device_template += "\n".join(member_entries) + "\n"

    device_template += "        super().__init__(name)\n"

    return class_stuff.get_class_name(device_template, class_name)


def sanitise_type_name(s: str):
    s = s.replace(" ", "_")
    s = s.replace("-", "_")
    return s


def sanitise_property_name(s: str):
    return sanitise_type_name(s).lower()


class Z2MDevicesParser(MqttSubscriber):
    def __init__(self, output: Path):
        super().__init__("bridge/devices")
        self.output: Path = output

    @override
    def _on_message(self, payload: Dict[Any, Any]) -> None:
        code = f"""# This file is autogenerated by emkyoot

from typing import List

from emkyoot.devices_client import Device, DevicesClient
from emkyoot.parameters import (
    NumericParameter,
    EnumParameter,
    SettableEnumParameter,
    QueryableNumericParameter,
    SettableAndQueryableToggleParameter,
    SettableAndQueryableNumericParameter,
    int_to_enum,
)

"""

        devices_code = """class AvailableDevices(DevicesClient):
    def __init__(self, no_query: bool = False):
        super().__init__(no_query)
"""

        for device in payload:
            device = DeviceDefinition.extract(device)

            if device is not None:
                class_name = generate_device(device)
                devices_code += f"        self.{sanitise_property_name(device.friendly_name)} = {class_name}('{device.friendly_name}')\n"

        code += enum_stuff.get_code_for_enum_class_definitions()
        code += stuff_stuff.get_code_for_enum_parameter_definitions()

        for name in class_stuff.get_class_names_in_order():
            code += class_stuff.get_class_code(name) + "\n"

        code += devices_code

        with open(self.output, "w") as f:
            f.write(code)

        message_loop.stop()


class DevicesGenerator(MqttClient):
    def __init__(self, output: Path):
        super().__init__()
        self.generator = Z2MDevicesParser(output)
