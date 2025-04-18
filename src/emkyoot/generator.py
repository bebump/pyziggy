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

import os
from pathlib import Path
from typing import List, Dict, Any, override, Tuple

from .code_line import CodeLine, CodeIndent
from .device_bases.device_base_requirements import (
    ParameterRequirement,
    BaseClassRequirement,
)
from .device_bases.device_base_rules import device_base_rules
from .message_loop import message_loop
from .mqtt_client import MqttClient, MqttSubscriber
from .parser import (
    NumericParameterDefinition,
    DeviceDefinition,
    EnumParameterDefinition,
    ParameterBaseDefinition,
    BinaryParameterDefinition,
    ToggleParameterDefinition,
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

    def get_code_for_enum_class_definitions(self) -> List[CodeLine]:
        code: List[CodeLine] = []

        if self.enum_name_for_enum_values_storage:
            code.append(
                CodeLine(f"from enum import Enum\n\n", CodeIndent.NONE, CodeIndent.NONE)
            )

        for (
            enum_values_storage,
            enum_name,
        ) in self.enum_name_for_enum_values_storage.items():
            code.append(
                CodeLine(
                    f"class {enum_name}(Enum):", CodeIndent.NONE, CodeIndent.INDENT
                )
            )

            for value in enum_values_storage.enum_values:
                code.append(
                    CodeLine(
                        f'{value.replace("/", "_")} = "{value}"',
                        CodeIndent.NONE,
                        CodeIndent.NONE,
                    )
                )

            code.append(CodeLine("\n", CodeIndent.NONE, CodeIndent.UNINDENT))

        return code


class EnumParameterGenerator:
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
                    CodeIndent.NONE,
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"def __init__(self, property: str, enum_values: List[str]):",
                    CodeIndent.NONE,
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"super().__init__(property, enum_values)",
                    CodeIndent.NONE,
                    CodeIndent.NONE,
                )
            )
            code.append(
                CodeLine(
                    f"self.enum_type = {enum}\n", CodeIndent.NONE, CodeIndent.UNINDENT
                )
            )

            code.append(
                CodeLine(
                    f"def get_enum_value(self) -> {enum}:",
                    CodeIndent.NONE,
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"return int_to_enum({enum}, int(self.get()))",
                    CodeIndent.NONE,
                    CodeIndent.UNINDENT,
                )
            )
            code.append(CodeLine("\n", CodeIndent.NONE, CodeIndent.UNINDENT))

        settable_enums = list(self.enum_names_for_settable)
        settable_enums.sort()

        for enum in settable_enums:
            code.append(
                CodeLine(
                    f"class {self.get_typename_for_settable_parameter_for(enum)}(SettableEnumParameter, {self.get_typename_for_parameter_for(enum)}):",
                    CodeIndent.NONE,
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"def set_enum_value(self, value: {enum}) -> None:",
                    CodeIndent.NONE,
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    "self.set(self._transform_mqtt_to_internal_value(value.value))",
                    CodeIndent.NONE,
                    CodeIndent.UNINDENT,
                )
            )
            code.append(CodeLine("", CodeIndent.NONE, CodeIndent.UNINDENT))

        return code


class ClassForImplementation:
    """
    Use this to deduplicate generated classes and give unique names to each.

    This class gives you a unique name for a class implementation code. If you give it class code
    it hasn't seen before, it gives you back a unique name for that class. It uses the provided
    base name and extends it until it results in a unique name.

    For class code it has already seen, it gives back the name that particular implementation got
    the first time.
    """

    def __init__(self):
        self.names: set[str] = set()
        self.name_for_code: Dict[str, str] = {}
        self.code_for_name: Dict[str, List[CodeLine]] = {}

    def get_class_name(self, code_lines: List[CodeLine], name_base: str) -> str:
        code = CodeLine.join("\n", code_lines)

        if code not in self.name_for_code.keys():
            name = name_base

            i = 1
            while True:
                if name not in self.names:
                    break

                name = name_base + f"Variant{i}"
                i += 1

            self.names.add(name)
            self.name_for_code[code] = name
            self.code_for_name[name] = code_lines

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


class ScopedCounter:
    counters: List[ScopedCounter] = []

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


# ==============================================================================
def get_function_param_names_for_param_type(parameter_type: type) -> List[str]:
    if parameter_type == NumericParameterDefinition:
        return [f"min{ScopedCounter.get()}", f"max{ScopedCounter.get()}"]

    if parameter_type == ToggleParameterDefinition:
        return []

    return []


def get_function_param_names(params: List[BaseClassRequirement | ParameterRequirement]):
    names: List[str] = []

    for param in params:
        if isinstance(param, ParameterRequirement):
            names.extend(get_function_param_names_for_param_type(type(param.parameter)))
        elif isinstance(param, BaseClassRequirement):
            names.extend(get_function_param_names(param.reqs))

    return names


def generate_parameter_param_names(parameter_type: type) -> List[str]:
    if parameter_type == EnumParameterDefinition:
        return [f"enum{ScopedCounter.get()}"]

    if parameter_type == BinaryParameterDefinition:
        return []

    if parameter_type == ToggleParameterDefinition:
        return []

    assert parameter_type == NumericParameterDefinition
    return [f"min{ScopedCounter.get()}", f"max{ScopedCounter.get()}"]


def generate_parameter_param_values(
    parameter: ParameterBaseDefinition, enum_class_generator: EnumClassGenerator
) -> List[str]:
    if isinstance(parameter, EnumParameterDefinition):
        assert parameter.enum_definition is not None
        enum_name = enum_class_generator.get_enum_class_name(
            parameter.enum_definition.values
        )
        return [f"[e.value for e in {enum_name}]"]

    if isinstance(parameter, BinaryParameterDefinition):
        return []

    if isinstance(parameter, ToggleParameterDefinition):
        return []

    assert isinstance(parameter, NumericParameterDefinition)
    return [str(parameter.value_min), str(parameter.value_max)]


def generate_parameter_member(
    parameter: ParameterBaseDefinition,
    parameter_substitutions: List[str],
    enum_class_gen: EnumClassGenerator,
    enum_param_gen: EnumParameterGenerator,
) -> CodeLine:
    def quoted(x):
        return f'"{x}"'

    if isinstance(parameter, EnumParameterDefinition):
        access_type = parameter.access_type
        assert parameter.enum_definition is not None
        enum_name = enum_class_gen.get_enum_class_name(parameter.enum_definition.values)

        if access_type.is_settable():
            return CodeLine(
                f"""self.{parameter.property} = {enum_param_gen.get_typename_for_settable_parameter_for(enum_name)}({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
            )

        return CodeLine(
            f"""self.{parameter.property} = {enum_param_gen.get_typename_for_parameter_for(enum_name)}({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
        )

    if isinstance(parameter, BinaryParameterDefinition):
        access_type = parameter.access_type

        if access_type.is_settable():
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = SettableAndQueryableBinaryParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
                )
            else:
                return CodeLine(
                    f"""self.{parameter.property} = SettableBinaryParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
                )
        else:
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = QueryableBinaryParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
                )

        return CodeLine(
            f"""self.{parameter.property} = BinaryParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
        )

    if isinstance(parameter, ToggleParameterDefinition):
        access_type = parameter.access_type

        if access_type.is_settable():
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = SettableAndQueryableToggleParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
                )
            else:
                return CodeLine(
                    f"""self.{parameter.property} = SettableToggleParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
                )
        else:
            if access_type.is_queryable():
                return CodeLine(
                    f"""self.{parameter.property} = QueryableToggleParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
                )

        return CodeLine(
            f"""self.{parameter.property} = ToggleParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
        )

    assert isinstance(parameter, NumericParameterDefinition)
    access_type = parameter.access_type

    if access_type.is_settable():
        if access_type.is_queryable():
            return CodeLine(
                f"""self.{parameter.property} = SettableAndQueryableNumericParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
            )
        else:
            return CodeLine(
                f"""self.{parameter.property} = SettableNumericParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
            )
    else:
        if access_type.is_queryable():
            return CodeLine(
                f"""self.{parameter.property} = QueryableNumericParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
            )

    return CodeLine(
        f"""self.{parameter.property} = NumericParameter({', '.join([quoted(parameter.property), *parameter_substitutions])})"""
    )


# ==============================================================================
def get_class_code(
    req: BaseClassRequirement,
    enum_class_gen: EnumClassGenerator,
    enum_param_gen: EnumParameterGenerator,
) -> List[CodeLine]:
    base_class_name = [
        req.name for req in req.reqs if isinstance(req, BaseClassRequirement)
    ]
    bases_code = f"({', '.join(base_class_name)})" if base_class_name else ""

    code: List[CodeLine] = [
        CodeLine(
            f"class {req.name}{bases_code}:",
            CodeIndent.NONE,
            CodeIndent.INDENT,
        )
    ]

    with ScopedCounter() as _:
        params = ["self"]
        params.extend(get_function_param_names(req.reqs))

        code.append(
            CodeLine(
                f"def __init__({', '.join(params)}):",
                CodeIndent.NONE,
                CodeIndent.INDENT,
            )
        )

    with ScopedCounter() as _:
        member_initalizers: List[CodeLine] = []

        for r in req.reqs:
            member_initalizers += get_init_code(r, enum_class_gen, enum_param_gen)

    if not member_initalizers:
        code += [CodeLine("pass", CodeIndent.NONE, CodeIndent.NONE)]

    code += member_initalizers
    code[-1].postindent = CodeIndent.UNINDENT2
    code += [CodeLine("", CodeIndent.NONE, CodeIndent.NONE)] * 2

    return code


def get_init_code(
    req: BaseClassRequirement | ParameterRequirement,
    enum_class_gen: EnumClassGenerator,
    enum_param_gen: EnumParameterGenerator,
    function_param_provider=get_function_param_names,
) -> List[CodeLine]:
    def get_init_code_for_base_class(req: BaseClassRequirement):
        code: List[CodeLine] = []

        params = ["self"]
        params.extend(function_param_provider(req.reqs))

        code.append(
            CodeLine(
                f"{req.name}.__init__({', '.join(params)})",
                CodeIndent.NONE,
                CodeIndent.NONE,
            )
        )

        return code

    if isinstance(req, BaseClassRequirement):
        return get_init_code_for_base_class(req)

    def get_init_code_for_parameter(req: ParameterRequirement):
        return [
            generate_parameter_member(
                req.parameter,
                generate_parameter_param_names(type(req.parameter)),
                enum_class_gen,
                enum_param_gen,
            )
        ]

    return get_init_code_for_parameter(req)


def get_function_values_for_param(parameter: ParameterBaseDefinition) -> List[str]:
    if isinstance(parameter, ToggleParameterDefinition):
        return []

    if isinstance(parameter, NumericParameterDefinition):
        return [str(parameter.value_min), str(parameter.value_max)]

    return []


def get_function_param_values(
    params: List[BaseClassRequirement | ParameterRequirement],
):
    values: List[str] = []

    for param in params:
        if isinstance(param, ParameterRequirement):
            values.extend(get_function_values_for_param(param.parameter))
        elif isinstance(param, BaseClassRequirement):
            values.extend(get_function_param_values(param.reqs))

    return values


def sanitize_type_name(s: str) -> str:
    assert len(s) > 0

    alphanumeric_with_underscore = "".join(c if c.isalnum() else "_" for c in s)

    if alphanumeric_with_underscore[0].isdigit():
        alphanumeric_with_underscore = "a" + alphanumeric_with_underscore

    return alphanumeric_with_underscore


def sanitize_property_name(s: str) -> str:
    return sanitize_type_name(s).lower()


# ==============================================================================
def generate_device_class(
    device: DeviceDefinition,
    enum_class_gen: EnumClassGenerator,
    enum_param_gen: EnumParameterGenerator,
) -> Tuple[List[CodeLine], str]:
    """
    Generates a class definition for the provided device.

    :return: A Tuple of the class code and a recommended name for the class.
    """
    device_template: List[CodeLine] = []

    base_classes = [act for act in [r.get_actualized(device.parameters) for r in device_base_rules] if act is not None]

    device_template += [
        CodeLine(
            f"class $class_name({', '.join(['Device', *[b.name for b in base_classes]])}):",
            CodeIndent.NONE,
            CodeIndent.INDENT,
        )
    ]
    device_template += [
        CodeLine("def __init__(self, name):", CodeIndent.NONE, CodeIndent.INDENT)
    ]

    with ScopedCounter() as _:
        for b in base_classes:
            device_template.extend(
                get_init_code(
                    b,
                    enum_class_gen,
                    enum_param_gen,
                    function_param_provider=get_function_param_values,
                )
            )

    member_entries = [
        generate_parameter_member(
            param,
            generate_parameter_param_values(param, enum_class_gen),
            enum_class_gen,
            enum_param_gen,
        )
        for param in device.parameters
        if param is not None
    ]
    device_template += member_entries

    device_template += [
        CodeLine("Device.__init__(self, name)", CodeIndent.NONE, CodeIndent.UNINDENT2)
    ]

    return (
        device_template,
        f"{sanitize_type_name(device.vendor)}_{sanitize_type_name(device.model_id)}",
    )


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

from emkyoot.device_bases import *

""",
            CodeIndent.NONE,
            CodeIndent.NONE,
        )
    )

    devices_code = [
        CodeLine(
            "class AvailableDevices(DevicesClient):", CodeIndent.NONE, CodeIndent.INDENT
        ),
        CodeLine(
            "def __init__(self, no_query: bool = False):",
            CodeIndent.NONE,
            CodeIndent.INDENT,
        ),
        CodeLine("super().__init__(no_query)", CodeIndent.NONE, CodeIndent.NONE),
    ]

    classes_code: Dict[str, None] = {}

    enum_class_gen = EnumClassGenerator()
    enum_param_gen = EnumParameterGenerator()
    class_for_impl = ClassForImplementation()

    for device_description in payload:
        device = DeviceDefinition.extract(device_description)

        if device is not None:
            class_name = class_for_impl.get_class_name(
                *generate_device_class(device, enum_class_gen, enum_param_gen)
            )
            devices_code.append(
                CodeLine(
                    f"self.{sanitize_property_name(device.friendly_name)} = {class_name}('{device.friendly_name}')",
                    CodeIndent.NONE,
                    CodeIndent.NONE,
                )
            )

    code += enum_class_gen.get_code_for_enum_class_definitions()
    code += enum_param_gen.get_code_for_enum_parameter_definitions()

    for name in class_for_impl.get_class_names_in_order():
        code.append(
            CodeLine(
                class_for_impl.get_class_code(name),
                CodeIndent.NONE,
                CodeIndent.NONE,
            )
        )

    code += devices_code

    with open(output.parent / "__init__.py", "w") as f:
        f.write("")

    with open(output, "w") as f:
        f.write(CodeLine.join("\n", code))


def generate_device_bases():
    enum_class_gen = EnumClassGenerator()
    enum_param_gen = EnumParameterGenerator()

    classes_code: Dict[str, None] = {}

    def visit(base: BaseClassRequirement):
        if base.name not in classes_code.keys():
            classes_code[
                CodeLine.join(
                    "\n", get_class_code(base, enum_class_gen, enum_param_gen)
                )
            ] = None

        for base_req in base.reqs:
            if isinstance(base_req, BaseClassRequirement):
                visit(base_req)

    def get_device_base_rules_reversed():
        result = device_base_rules.copy()
        result.reverse()
        return result

    device_base_rules_reversed = get_device_base_rules_reversed()

    for b in device_base_rules_reversed:
        visit(b)

    code = """# This file is autogenerated by emkyoot
# See emkyoot.generator.generate_device_bases()

from emkyoot.parameters import (
    NumericParameter,
    QueryableNumericParameter,
    SettableAndQueryableNumericParameter,
    EnumParameter,
    SettableEnumParameter,
    BinaryParameter,
    SettableToggleParameter,
    SettableAndQueryableToggleParameter,
    int_to_enum,
)

""" + "".join(
        classes_code.keys()
    )

    all_imports: List[CodeLine] = [
        CodeLine("__all__ = [", CodeIndent.NONE, CodeIndent.INDENT)
    ]

    for b in device_base_rules:
        if isinstance(b, BaseClassRequirement):
            all_imports += [CodeLine(f"'{b.name}',", CodeIndent.NONE, CodeIndent.NONE)]

    all_imports += [CodeLine("]", CodeIndent.NONE, CodeIndent.UNINDENT)]

    code += CodeLine.join("\n", all_imports)

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

    with open(rel_to_py("device_bases", "__init__.py"), "w") as f:
        f.write(code)


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
