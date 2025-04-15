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

from enum import IntEnum
from pathlib import Path
from typing import List, Dict, Any, override

from .device_definition_parser import (
    NumericParameterDefinition,
    DeviceDefinition,
    EnumParameterDefinition,
    ParameterBaseDefinition,
    BinaryParameterDefinition,
    ToggleParameterDefinition,
)
from .message_loop import message_loop
from .mqtt_client import MqttClient, MqttSubscriber


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

    def get_code_for_enum_class_definitions(self) -> List[CodeLine]:
        code: List[CodeLine] = []

        if self.enum_name_for_enum_values_storage:
            code.append(
                CodeLine(f"from enum import Enum\n\n", Indent.NONE, Indent.NONE)
            )

        for (
            enum_values_storage,
            enum_name,
        ) in self.enum_name_for_enum_values_storage.items():
            code.append(
                CodeLine(f"class {enum_name}(Enum):", Indent.NONE, Indent.INDENT)
            )

            for value in enum_values_storage.enum_values:
                code.append(
                    CodeLine(
                        f'{value.replace("/", "_")} = "{value}"',
                        Indent.NONE,
                        Indent.NONE,
                    )
                )

            code.append(CodeLine("\n", Indent.NONE, Indent.UNINDENT))

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

    def get_code_for_enum_parameter_definitions(self) -> List[CodeLine]:
        code: List[CodeLine] = []

        enums = list(self.enum_names_for_not_settable)
        enums.sort()

        for enum in enums:
            code.append(
                CodeLine(
                    f"class {self.get_typename_for_parameter_for(enum)}(EnumParameter):",
                    Indent.NONE,
                    Indent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"def __init__(self, property: str, enum_values: List[str]):",
                    Indent.NONE,
                    Indent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"super().__init__(property, enum_values)",
                    Indent.NONE,
                    Indent.NONE,
                )
            )
            code.append(
                CodeLine(f"self.enum_type = {enum}\n", Indent.NONE, Indent.UNINDENT)
            )

            code.append(
                CodeLine(
                    f"def get_enum_value(self) -> {enum}:", Indent.NONE, Indent.INDENT
                )
            )
            code.append(
                CodeLine(
                    f"return int_to_enum({enum}, int(self.get()))",
                    Indent.NONE,
                    Indent.UNINDENT,
                )
            )
            code.append(CodeLine("\n", Indent.NONE, Indent.UNINDENT))

        settable_enums = list(self.enum_names_for_settable)
        settable_enums.sort()

        for enum in settable_enums:
            code.append(
                CodeLine(
                    f"class {self.get_typename_for_settable_parameter_for(enum)}(SettableEnumParameter, {self.get_typename_for_parameter_for(enum)}):",
                    Indent.NONE,
                    Indent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"def set_enum_value(self, value: {enum}) -> None:",
                    Indent.NONE,
                    Indent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    "self.set(self._transform_mqtt_to_internal_value(value.value))",
                    Indent.NONE,
                    Indent.UNINDENT,
                )
            )
            code.append(CodeLine("", Indent.NONE, Indent.UNINDENT))

        return code


enum_stuff = EnumClassGenerator()
class_stuff = ClassStuff()
stuff_stuff = StuffStuff()


class Indent(IntEnum):
    NONE = 0
    INDENT = 1
    UNINDENT = 2
    UNINDENT2 = 3


class CodeLine:
    def __init__(
        self,
        line: str,
        preindent: Indent = Indent.NONE,
        postindent: Indent = Indent.NONE,
    ):
        assert isinstance(line, str)
        self.line = line
        self.preindent = preindent
        self.postindent = postindent

    def __str__(self):
        return self.line

    # TODO: Rename to join
    @staticmethod
    def join(separator: str, lines: List[CodeLine]) -> str:
        result = ""
        indent_level = 0

        for line in lines:
            if line.preindent == Indent.INDENT:
                indent_level += 1
            elif line.preindent == Indent.UNINDENT:
                indent_level -= 1
            elif line.preindent == Indent.UNINDENT2:
                indent_level -= 2

            if indent_level < 0:
                indent_level = 0

            result += "    " * indent_level + str(line) + separator

            if line.postindent == Indent.INDENT:
                indent_level += 1
            elif line.postindent == Indent.UNINDENT:
                indent_level -= 1
            elif line.postindent == Indent.UNINDENT2:
                indent_level -= 2

        return result


def generate_parameter_param_names(parameter: ParameterBaseDefinition) -> str:
    if isinstance(parameter, EnumParameterDefinition):
        return [f"enum{ScopedCounter.get()}"]

    if isinstance(parameter, BinaryParameterDefinition):
        return []

    if isinstance(parameter, ToggleParameterDefinition):
        return []

    if isinstance(parameter, NumericParameterDefinition):
        return [f"min{ScopedCounter.get()}", f"max{ScopedCounter.get()}"]


def generate_parameter_param_values(parameter: ParameterBaseDefinition) -> str:
    if isinstance(parameter, EnumParameterDefinition):
        enum_name = enum_stuff.get_enum_class_name(parameter.enum_definition.values)
        return [f"[e.value for e in {enum_name}]"]

    if isinstance(parameter, BinaryParameterDefinition):
        return []

    if isinstance(parameter, ToggleParameterDefinition):
        return []

    if isinstance(parameter, NumericParameterDefinition):
        return [str(parameter.value_min), str(parameter.value_max)]


def generate_parameter_member(
    parameter: ParameterBaseDefinition, kind=generate_parameter_param_values
) -> CodeLine:
    params = kind(parameter)

    def quoted(x):
        return f'"{x}"'

    if isinstance(parameter, EnumParameterDefinition):
        access_type = parameter.access_type
        enum_name = enum_stuff.get_enum_class_name(parameter.enum_definition.values)

        if access_type.is_settable():
            return CodeLine(
                f"""self.{parameter.property} = {stuff_stuff.get_typename_for_settable_parameter_for(enum_name)}({', '.join([quoted(parameter.property), *params])})"""
            )

        return CodeLine(
            f"""self.{parameter.property} = {stuff_stuff.get_typename_for_parameter_for(enum_name)}({', '.join([quoted(parameter.property), *params])})"""
        )

    if isinstance(parameter, BinaryParameterDefinition):
        access_type = parameter.access_type

        if access_type.is_settable():
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = SettableAndQueryableBinaryParameter({', '.join([quoted(parameter.property), *params])})"""
                )
            else:
                return CodeLine(
                    f"""self.{parameter.property} = SettableBinaryParameter({', '.join([quoted(parameter.property), *params])})"""
                )
        else:
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = QueryableBinaryParameter({', '.join([quoted(parameter.property), *params])})"""
                )

        return CodeLine(
            f"""self.{parameter.property} = BinaryParameter({', '.join([quoted(parameter.property), *params])})"""
        )

    if isinstance(parameter, ToggleParameterDefinition):
        access_type = parameter.access_type

        if access_type.is_settable():
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = SettableAndQueryableToggleParameter({', '.join([quoted(parameter.property), *params])})"""
                )
            else:
                return CodeLine(
                    f"""self.{parameter.property} = SettableToggleParameter({', '.join([quoted(parameter.property), *params])})"""
                )
        else:
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = QueryableToggleParameter({', '.join([quoted(parameter.property), *params])})"""
                )

        return CodeLine(
            f"""self.{parameter.property} = ToggleParameter({', '.join([quoted(parameter.property), *params])})"""
        )

    if isinstance(parameter, NumericParameterDefinition):
        access_type = parameter.access_type

        if access_type.is_settable():
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = SettableAndQueryableNumericParameter({', '.join([quoted(parameter.property), *params])})"""
                )
            else:
                return CodeLine(
                    f"""self.{parameter.property} = SettableNumericParameter({', '.join([quoted(parameter.property), *params])})"""
                )
        else:
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = QueryableNumericParameter({', '.join([quoted(parameter.property), *params])})"""
                )

        return CodeLine(
            f"""self.{parameter.property} = NumericParameter({', '.join([quoted(parameter.property), *params])})"""
        )


def get_device_class_name_base(device: DeviceDefinition) -> str:
    return f"{sanitize_type_name(device.vendor)}_{sanitize_type_name(device.model_id)}"


class ParameterRequirement:
    def __init__(self, property: str, parameter_type: type, check: callable):
        self.property = property
        self.parameter_type = parameter_type
        self.check = check
        self.parameter: parameter_type | None = None

    def is_applicable(self, parameters: List[ParameterBaseDefinition]) -> bool:
        def find_param_index():
            for i, param in enumerate(parameters):
                if param.property == self.property:
                    return i

            return -1

        param_index = find_param_index()

        if param_index == -1:
            return False

        parameter = parameters[param_index]

        if not isinstance(parameter, self.parameter_type):
            return False

        if not self.check(parameter):
            return False

        self.parameter = parameter
        del parameters[param_index]

        return True

    def get_init_code(self):
        return [
            generate_parameter_member(
                self.parameter, kind=generate_parameter_param_names
            )
        ]


# ==============================================================================
def get_function_param_names_for_param_type(parameter_type: type) -> List[str]:
    if parameter_type == NumericParameterDefinition:
        return [f"min{ScopedCounter.get()}", f"max{ScopedCounter.get()}"]

    if parameter_type == ToggleParameterDefinition:
        return []

    return []


def get_function_param_names(params: List[ParameterRequirement | ParameterRequirement]):
    names: List[str] = []

    for param in params:
        if isinstance(param, ParameterRequirement):
            names.extend(get_function_param_names_for_param_type(param.parameter_type))
        elif isinstance(param, Specialization):
            names.extend(get_function_param_names(param.reqs))

    return names


# ==============================================================================
def get_function_values_for_param(parameter: ParameterBaseDefinition) -> List[str]:
    if isinstance(parameter, ToggleParameterDefinition):
        return []

    if isinstance(parameter, NumericParameterDefinition):
        return [str(parameter.value_min), str(parameter.value_max)]

    return []


def get_function_param_values(
    params: List[ParameterRequirement | ParameterRequirement],
):
    values: List[str] = []

    for param in params:
        if isinstance(param, ParameterRequirement):
            values.extend(get_function_values_for_param(param.parameter))
        elif isinstance(param, Specialization):
            values.extend(get_function_param_values(param.reqs))

    return values


class Specialization:
    def __init__(self, name: str, reqs: List[Specialization | ParameterRequirement]):
        self.name = name
        self.reqs = reqs

    def is_applicable(self, parameters: List[ParameterBaseDefinition]) -> bool:
        consumable_parameters = parameters.copy()

        for req in self.reqs:
            if isinstance(req, ParameterRequirement) or isinstance(req, Specialization):
                if not req.is_applicable(consumable_parameters):
                    return False

        parameters[:] = consumable_parameters[:]
        return True

    def code_for_params(self):
        code: List[CodeLine] = []

        for req in self.reqs:
            if isinstance(req, ParameterRequirement):
                code.append(
                    CodeLine(f"{get_parameters_string_for_constructor(req.parameter)}")
                )

        return code

    def get_class_code(self) -> List[CodeLine]:
        base_classes = [
            req.name for req in self.reqs if isinstance(req, Specialization)
        ]
        bases_code = f"({', '.join(base_classes)})" if base_classes else ""

        code: List[CodeLine] = [
            CodeLine(
                f"class {self.name}{bases_code}:",
                Indent.NONE,
                Indent.INDENT,
            )
        ]

        with ScopedCounter() as _:
            params = ["self"]
            params.extend(get_function_param_names(self.reqs))

            code.append(
                CodeLine(
                    f"def __init__({', '.join(params)}):", Indent.NONE, Indent.INDENT
                )
            )

        with ScopedCounter() as _:
            for req in self.reqs:
                code.extend(req.get_init_code())

        return code

    def get_init_code(self, function_param_provider=get_function_param_names):
        code: List[CodeLine] = []

        params = ["self"]
        params.extend(function_param_provider(self.reqs))

        code.append(
            CodeLine(
                f"{self.name}.__init__({', '.join(params)})", Indent.NONE, Indent.NONE
            )
        )

        return code


dimmable_light = Specialization(
    "DimmableLight",
    [
        ParameterRequirement(
            "state", ToggleParameterDefinition, lambda x: x.access_type.is_settable()
        ),
        ParameterRequirement(
            "brightness",
            NumericParameterDefinition,
            lambda x: x.access_type.is_settable(),
        ),
    ],
)

light_with_color_temp = Specialization(
    "LightWithColorTemp",
    [
        dimmable_light,
        ParameterRequirement(
            "color_temp",
            NumericParameterDefinition,
            lambda x: x.access_type.is_settable(),
        ),
    ],
)


class ScopedCounter:
    counters = []

    def __init__(self):
        self.count = 0
        ScopedCounter.counters.append(self)

    @staticmethod
    def get():
        ScopedCounter.counters[-1].count += 1
        return ScopedCounter.counters[-1].count - 1

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.counters.remove(self)
        return False


def get_parameters_string_for_constructor(x):
    if isinstance(x, ToggleParameterDefinition):
        return ""

    if isinstance(x, NumericParameterDefinition):
        return f"{x.value_min}, {x.value_max}"


def collect_specialisation_classes_code(specializations, classes_code: Dict[str, None]):
    def visit(spec: Specialization):
        if spec.name not in classes_code.keys():
            classes_code[CodeLine.join("\n", spec.get_class_code())] = None

        for req in spec.reqs:
            if isinstance(req, Specialization):
                visit(req)

    for specialization in specializations:
        visit(specialization)


def generate_device(device: DeviceDefinition, classes_code: Dict[str, None]):
    specializations = [light_with_color_temp, dimmable_light]
    base_classes = [s for s in specializations if s.is_applicable(device.parameters)]
    collect_specialisation_classes_code(base_classes, classes_code)

    member_entries = []

    properties = {param.property: param for param in device.parameters}

    for _, parameter in properties.items():
        p = generate_parameter_member(parameter)

        if p is not None:
            member_entries.append(p)

    class_name_base = get_device_class_name_base(device)

    device_template = []

    device_template.append(
        CodeLine(
            f"class $class_name({', '.join(['Device', *[b.name for b in base_classes]])}):",
            Indent.NONE,
            Indent.INDENT,
        )
    )

    device_template.append(
        CodeLine("def __init__(self, name):", Indent.NONE, Indent.INDENT)
    )

    with ScopedCounter() as _:
        for b in base_classes:
            device_template.extend(
                b.get_init_code(function_param_provider=get_function_param_values)
            )

    if member_entries:
        device_template.extend(member_entries)

    device_template.append(
        CodeLine("Device.__init__(self, name)", Indent.NONE, Indent.UNINDENT2)
    )

    return class_stuff.get_class_name(
        CodeLine.join("\n", device_template), class_name_base
    )


def sanitize_type_name(s: str):
    assert len(s) > 0

    alphanumeric_with_underscore = "".join(c if c.isalnum() else "_" for c in s)

    if alphanumeric_with_underscore[0].isdigit():
        alphanumeric_with_underscore = "a" + alphanumeric_with_underscore

    return alphanumeric_with_underscore


def sanitize_property_name(s: str):
    return sanitize_type_name(s).lower()


def generate_devices_client(payload: Dict[Any, Any], output: Path):
    code: List[CodeLine] = []
    code.append(
        CodeLine(
            f"""# This file is autogenerated by emkyoot

from typing import List

from emkyoot.devices_client import Device, DevicesClient
from emkyoot.parameters import (
    NumericParameter,
    QueryableNumericParameter,
    SettableAndQueryableNumericParameter,
    EnumParameter,
    SettableEnumParameter,
    BinaryParameter,
    SettableAndQueryableToggleParameter,
    int_to_enum,
)

from .device_bases import *

""",
            Indent.NONE,
            Indent.NONE,
        )
    )

    devices_code = [
        CodeLine("class AvailableDevices(DevicesClient):", Indent.NONE, Indent.INDENT),
        CodeLine(
            "def __init__(self, no_query: bool = False):", Indent.NONE, Indent.INDENT
        ),
        CodeLine("super().__init__(no_query)", Indent.NONE, Indent.NONE),
    ]

    classes_code: Dict[str, None] = {}

    for device in payload:
        device = DeviceDefinition.extract(device)

        if device is not None:
            class_name = generate_device(device, classes_code)
            devices_code.append(
                CodeLine(
                    f"self.{sanitize_property_name(device.friendly_name)} = {class_name}('{device.friendly_name}')",
                    Indent.NONE,
                    Indent.NONE,
                )
            )

    code += enum_stuff.get_code_for_enum_class_definitions()
    code += stuff_stuff.get_code_for_enum_parameter_definitions()

    for name in class_stuff.get_class_names_in_order():
        code.append(
            CodeLine(class_stuff.get_class_code(name) + "\n", Indent.NONE, Indent.NONE)
        )

    code += devices_code

    with open(output.parent / "__init__.py", "w") as f:
        f.write("")

    with open(output.parent / "device_bases.py", "w") as f:
        f.write("""# This file is autogenerated by emkyoot

from emkyoot.parameters import (
    NumericParameter,
    QueryableNumericParameter,
    SettableAndQueryableNumericParameter,
    EnumParameter,
    SettableEnumParameter,
    BinaryParameter,
    SettableAndQueryableToggleParameter,
    int_to_enum,
)


""")

        f.write(
            "\n\n".join(
                [class_code for class_code in reversed(list(classes_code.keys()))]
            )
            + "\n"
        )

    with open(output, "w") as f:
        f.write(CodeLine.join("\n", code))


class Z2MDevicesParser(MqttSubscriber):
    def __init__(self, output: Path):
        super().__init__("bridge/devices")
        self.output: Path = output

    @override
    def _on_message(self, payload: Dict[Any, Any]) -> None:
        generate_devices_client(payload, self.output)
        message_loop.stop()


class DevicesGenerator(MqttClient):
    def __init__(self, output: Path):
        super().__init__()
        self.generator = Z2MDevicesParser(output)
