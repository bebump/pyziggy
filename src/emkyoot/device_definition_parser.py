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

from typing import List, Union, Dict, Any, Optional


class ParameterAccessType:
    def __init__(self, flags: int):
        self._flags = flags

    def is_queryable(self) -> bool:
        """Returns true if the parameter can be queried with the /get command"""
        return self._flags & 0b100 != 0

    def is_settable(self) -> bool:
        """Returns true if the parameter can be set with the /set command"""
        return self._flags & 0b10 != 0


class ParameterBaseDefinition:
    def __init__(self, property: str, access_type: int):
        self.property: str = property
        self.access_type = ParameterAccessType(access_type)


class NumericParameterDefinition(ParameterBaseDefinition):
    def __init__(self, property: str, access_type: int, value_min: int, value_max: int):
        super().__init__(property, access_type)
        self.value_min = value_min
        self.value_max = value_max

    def __repr__(self):
        return f"NumericParameterDefinition({self.property}, {self.value_min}, {self.value_max})"

    @staticmethod
    def extract(feature: Dict[str, Any]):
        try:
            if feature["type"] != "numeric":
                return None

            return NumericParameterDefinition(
                feature["property"],
                feature["access"],
                feature["value_min"],
                feature["value_max"],
            )
        except:
            return None


class ToggleParameterDefinition(NumericParameterDefinition):
    def __init__(self, property: str, access_type: int):
        super().__init__(property, access_type, 0, 1)

    def __repr__(self):
        return f"ToggleParameterDefinition({self.property})"

    @staticmethod
    def extract(feature: Dict[str, Any]):
        try:
            if (
                feature["value_off"] == "OFF"
                and feature["value_on"] == "ON"
                and feature["value_toggle"] == "TOGGLE"
            ):
                return ToggleParameterDefinition(feature["property"], feature["access"])
        except:
            return None


class StringEnumDefinition:
    def __init__(self, values: List[str]):
        values.sort()
        self.values: List[str] = values


class EnumParameterDefinition(NumericParameterDefinition):
    def __init__(self, property: str, access_type: int, enumeration: List[str]):
        super().__init__(property, access_type, 0, len(enumeration))
        self.enum_definition: StringEnumDefinition = StringEnumDefinition(enumeration)

    def __repr__(self):
        return (
            f"EnumParameterDefinition({self.property}, {self.enum_definition.values})"
        )

    @staticmethod
    def extract(feature: Dict[str, Any]):
        try:
            if feature["type"] != "enum":
                return None

            return EnumParameterDefinition(
                feature["property"], feature["access"], feature["values"]
            )
        except Exception as e:
            print(e)
            return None


parameter_type_definitions = [
    NumericParameterDefinition,
    ToggleParameterDefinition,
    EnumParameterDefinition,
]


def extract_parameter(
    node,
) -> Optional[
    Union[
        NumericParameterDefinition, ToggleParameterDefinition, EnumParameterDefinition
    ]
]:
    for extractor in parameter_type_definitions:
        parameter = extractor.extract(node)  # type: ignore[attr-defined]

        if parameter is not None:
            return parameter

    return None


class DeviceDefinition:
    def __init__(
        self,
        friendly_name: str,
        model_id: str,
        description: str,
        vendor: str,
        parameters: List[ParameterBaseDefinition],
    ):
        self.friendly_name: str = friendly_name
        self.model_id: str = model_id
        self.description: str = description
        self.vendor: str = vendor
        self.parameters: List[ParameterBaseDefinition] = parameters
        self.parameters.sort(key=lambda obj: obj.property)

    def __str__(self):
        s = f"DeviceDefinition({self.friendly_name})"

        for p in self.parameters:
            s += f"\n  {p}"

            if p.access_type.is_queryable():
                s += " /get"

            if p.access_type.is_settable():
                s += " /set"

        return s

    @staticmethod
    def extract(item_in_bridge_per_devices_mqtt):
        try:
            friendly_name = item_in_bridge_per_devices_mqtt["friendly_name"]
            model_id = item_in_bridge_per_devices_mqtt["model_id"]
            description = item_in_bridge_per_devices_mqtt["definition"]["description"]
            vendor = item_in_bridge_per_devices_mqtt["definition"]["vendor"]
            exposes = item_in_bridge_per_devices_mqtt["definition"]["exposes"]
            parameters: List[ParameterBaseDefinition] = (
                DeviceDefinition.extract_parameters(exposes)
            )

            return DeviceDefinition(
                friendly_name, model_id, description, vendor, parameters
            )

        except:
            pass

    @staticmethod
    def extract_parameters(
        exposes_in_device_definition,
    ) -> List[ParameterBaseDefinition]:
        parameters: List[ParameterBaseDefinition] = []

        for item in exposes_in_device_definition:
            if item.get("type") == "light":
                features = item.get("features")

                if features is not None:
                    for node in features:
                        p = extract_parameter(node)

                        if p is not None:
                            parameters.append(p)

            else:
                p = extract_parameter(item)

                if p is not None:
                    parameters.append(p)

        return parameters
