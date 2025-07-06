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

import os
from pathlib import Path
from typing import List, Dict, Any, override

from .code_line import CodeLine, CodeIndent
from .device_bases.device_base_requirements import (
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
    CompositeParameterDefinition,
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
            code.append(CodeLine(f"from enum import Enum\n\n"))

        for (
            enum_values_storage,
            enum_name,
        ) in self.enum_name_for_enum_values_storage.items():
            code.append(CodeLine(f"class {enum_name}(Enum):", CodeIndent.INDENT))

            for value in enum_values_storage.enum_values:
                code.append(CodeLine(f'{value.replace("/", "_")} = "{value}"'))

            code.append(CodeLine("\n", CodeIndent.UNINDENT))

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
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"def __init__(self, property: str, enum_values: List[str]):",
                    CodeIndent.INDENT,
                )
            )
            code.append(CodeLine(f"super().__init__(property, enum_values)"))
            code.append(CodeLine(f"self.enum_type = {enum}\n", CodeIndent.UNINDENT))

            code.append(
                CodeLine(
                    f"def get_enum_value(self) -> {enum}:",
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"return int_to_enum({enum}, int(self.get()))",
                    CodeIndent.UNINDENT,
                )
            )
            code.append(CodeLine("\n", CodeIndent.UNINDENT))

        settable_enums = list(self.enum_names_for_settable)
        settable_enums.sort()

        for enum in settable_enums:
            code.append(
                CodeLine(
                    f"class {self.get_typename_for_settable_parameter_for(enum)}(SettableEnumParameter, {self.get_typename_for_parameter_for(enum)}):",
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    f"def set_enum_value(self, value: {enum}) -> None:",
                    CodeIndent.INDENT,
                )
            )
            code.append(
                CodeLine(
                    "self.set(self._transform_mqtt_to_internal_value(value.value))",
                    CodeIndent.UNINDENT,
                )
            )
            code.append(CodeLine("\n", CodeIndent.UNINDENT))

        return code


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


def sanitize_for_type_name(s: str) -> str:
    assert len(s) > 0

    alphanumeric_with_underscore = "".join(c if c.isalnum() else "_" for c in s)

    if alphanumeric_with_underscore[0].isdigit():
        alphanumeric_with_underscore = "a" + alphanumeric_with_underscore

    return alphanumeric_with_underscore


def sanitize_for_property_name(s: str) -> str:
    return sanitize_for_type_name(s).lower()


class ClassGenerator:
    def __init__(self):
        self._enum_class_generator = EnumClassGenerator()
        self._enum_parameter_generator = EnumParameterGenerator()

        # The base classes are stored as an extra, tacked on first CodeLine
        self._classes: Dict[str, List[CodeLine]] = {}

    def generate_class(
        self,
        name_prefix: str,
        init_code: List[CodeLine],
        base_class_names: List[str] = [],
        avoid_duplicate_class_impls: bool = False,
    ):
        """

        :param name_prefix:
        :param init_code:
        :param base_class_names:
        :param avoid_duplicate_class_impls: If a class exists with the same implementation then it
                                            will be returned, even if it has a different name.
        :return:
        """

        init_code = [CodeLine(", ".join(base_class_names))] + init_code

        if avoid_duplicate_class_impls:
            for k, v in self._classes.items():
                if v == init_code:
                    return k

        i = 0
        class_name = name_prefix

        while True:
            if class_name not in self._classes.keys():
                self._classes[class_name] = init_code

            if self._classes[class_name] == init_code:
                return class_name

            class_name = f"{name_prefix}{i}"
            i += 1

    def get_generated_classes(self):
        classes: Dict[str, List[CodeLine]] = {}

        for name, lines in self._classes.items():
            name, lines

            inherits = f"({lines[0].line})" if lines[0].line else ""

            lines = [CodeLine(f"class {name}{inherits}:", CodeIndent.INDENT)] + lines[
                1:
            ]

            if lines[-1] == CodeLine("", CodeIndent.UNINDENT):
                lines[-1] = CodeLine("", CodeIndent.UNINDENT2)
            elif lines[-1] == CodeLine("\n", CodeIndent.UNINDENT):
                lines[-1] = CodeLine("\n", CodeIndent.UNINDENT2)
            else:
                lines += [CodeLine("", CodeIndent.UNINDENT)]

            classes[name] = lines

        return classes

    def get_enum_class_name(self, values: List[str]):
        return self._enum_class_generator.get_enum_class_name(values)

    def get_enum_parameter_name(self, values: List[str], settable: bool):
        enum_class_name = self._enum_class_generator.get_enum_class_name(values)

        if settable:
            return (
                self._enum_parameter_generator.get_typename_for_settable_parameter_for(
                    enum_class_name
                )
            )

        return self._enum_parameter_generator.get_typename_for_parameter_for(
            enum_class_name
        )


class ClassSkeletonArg:
    def __init__(self, typename: str, value: str | None):
        self.typename: str = typename
        self.value: str | None = value


class ClassSkeletonEntry:
    def __init__(
        self,
        member_name: str | None,
        initializer_expr: str,
        arguments: List[ClassSkeletonArg],
    ):
        self.member_name: str | None = member_name
        self.initializer_expr: str = initializer_expr
        self.arguments: List[ClassSkeletonArg] = arguments


class ClassSkeleton:
    @staticmethod
    def value_or_arg(value_opt: str | None):
        if value_opt is None:
            return f"arg{ScopedCounter.get()}"

        return value_opt

    def __init__(self, generator: ClassGenerator):
        self.generator: ClassGenerator = generator
        self.entries: List[ClassSkeletonEntry] = []

    def add_entry(self, entry: ClassSkeletonEntry):
        assert entry.member_name is None or entry.member_name not in {
            e.member_name for e in self.entries if e.member_name is not None
        }
        self.entries.append(entry)

    def append(self, other: ClassSkeleton):
        assert self.generator == other.generator

        for entry in other.entries:
            self.add_entry(entry)

    def get_init(self):
        init: List[CodeLine] = []

        for entry in self.entries:
            line = ""

            if entry.member_name is not None:
                line += f"self.{entry.member_name} = "

            args_str = ", ".join(
                [ClassSkeleton.value_or_arg(arg.value) for arg in entry.arguments]
            )

            if not args_str:
                line += entry.initializer_expr.replace(",$args", "").replace(
                    ", $args", ""
                )
            else:
                line += entry.initializer_expr.replace("$args", args_str)

            init.append(CodeLine(line))

        return init

    def get_init_args(self) -> List[ClassSkeletonArg]:
        args: List[ClassSkeletonArg] = []

        for e in self.entries:
            for a in e.arguments:
                args.append(a)

        return args

    def get_init_arg_values(self):
        return [ClassSkeleton.value_or_arg(a.value) for a in self.get_init_args()]


def get_initialization_arguments(
    cg: ClassGenerator, parameter: ParameterBaseDefinition
):
    def str_or_none(value_opt: Any) -> str | None:
        if value_opt is None:
            return None

        return str(value_opt)

    if isinstance(parameter, EnumParameterDefinition):
        assert parameter.enum_definition is not None
        assert parameter.enum_definition.values is not None
        return [
            ClassSkeletonArg(
                "list[str]",
                f"[e.value for e in {cg.get_enum_class_name(parameter.enum_definition.values)}]",
            )
        ]

    elif isinstance(parameter, BinaryParameterDefinition):
        return []
    elif isinstance(parameter, ToggleParameterDefinition):
        return []
    elif isinstance(parameter, NumericParameterDefinition):
        return [
            ClassSkeletonArg("int", str_or_none(parameter.value_min)),
            ClassSkeletonArg("int", str_or_none(parameter.value_max)),
        ]
    assert isinstance(parameter, CompositeParameterDefinition)
    args: List[ClassSkeletonArg] = []

    for p in parameter.parameters:
        args += get_initialization_arguments(cg, p)

    return args


def quoted(x):
    return f'"{x}"'


def generate_class_skeleton(
    cg: ClassGenerator, parameters: List[ParameterBaseDefinition]
):
    skeleton = ClassSkeleton(cg)

    for parameter in parameters:
        access = parameter.access_type

        if isinstance(parameter, EnumParameterDefinition):
            assert parameter.enum_definition is not None
            skeleton.add_entry(
                ClassSkeletonEntry(
                    parameter.name,
                    f"{cg.get_enum_parameter_name(parameter.enum_definition.values, settable=access.is_settable())}({quoted(parameter.property)}, $args)",
                    get_initialization_arguments(cg, parameter),
                )
            )

        elif isinstance(parameter, BinaryParameterDefinition):

            def get_typename_for_parameter():
                if access.is_settable() and access.is_queryable():
                    return "SettableAndQueryableBinaryParameter"
                elif access.is_settable():
                    return "SettableBinaryParameter"
                elif access.is_queryable():
                    return "QueryableBinaryParameter"

                return "BinaryParameter"

            skeleton.add_entry(
                ClassSkeletonEntry(
                    parameter.name,
                    f"{get_typename_for_parameter()}({quoted(parameter.property)}, $args)",
                    get_initialization_arguments(cg, parameter),
                )
            )

        elif isinstance(parameter, ToggleParameterDefinition):

            def get_typename_for_parameter():
                if access.is_settable() and access.is_queryable():
                    return "SettableAndQueryableToggleParameter"
                elif access.is_settable():
                    return "SettableToggleParameter"
                elif access.is_queryable():
                    return "QueryableToggleParameter"

                return "ToggleParameter"

            skeleton.add_entry(
                ClassSkeletonEntry(
                    parameter.name,
                    f"{get_typename_for_parameter()}({quoted(parameter.property)}, $args)",
                    get_initialization_arguments(cg, parameter),
                )
            )

        elif isinstance(parameter, NumericParameterDefinition):

            def get_typename_for_parameter():
                if access.is_settable() and access.is_queryable():
                    return "SettableAndQueryableNumericParameter"
                elif access.is_settable():
                    return "SettableNumericParameter"
                elif access.is_queryable():
                    return "QueryableNumericParameter"

                return "NumericParameter"

            skeleton.add_entry(
                ClassSkeletonEntry(
                    parameter.name,
                    f"{get_typename_for_parameter()}({quoted(parameter.property)}, $args)",
                    get_initialization_arguments(cg, parameter),
                )
            )

        elif isinstance(parameter, CompositeParameterDefinition):
            composite_skeleton = generate_class_skeleton(cg, parameter.parameters)

            for e in composite_skeleton.entries:
                for a in e.arguments:
                    a.value = None

            composite_skeleton.add_entry(
                ClassSkeletonEntry(
                    None,
                    f"CompositeParameter.__init__(self, property)",
                    [],
                )
            )

            init_args = ["self", "property: str"]

            with ScopedCounter() as _:
                init_args += composite_skeleton.get_init_arg_values()

            composite_class_name = ""

            with ScopedCounter() as _:
                composite_class_name = cg.generate_class(
                    "CompositeParameterVariant",
                    [
                        CodeLine(
                            f"def __init__({', '.join(init_args)}):",
                            CodeIndent.INDENT,
                        )
                    ]
                    + composite_skeleton.get_init()
                    + [CodeLine("\n", CodeIndent.UNINDENT)],
                    base_class_names=["CompositeParameter"],
                )

            skeleton.add_entry(
                ClassSkeletonEntry(
                    parameter.name,
                    f"{composite_class_name}({quoted(parameter.property)}, $args)",
                    get_initialization_arguments(cg, parameter),
                )
            )

    return skeleton


def generate_devices_client(payload: Dict[Any, Any], output: Path):
    code: List[CodeLine] = []
    code.append(
        CodeLine(
            f"""# This file is autogenerated by pyziggy

from typing import List

from pyziggy.devices_client import Device, DevicesClient
from pyziggy.parameters import (
    NumericParameter,
    QueryableNumericParameter,
    SettableAndQueryableNumericParameter,
    EnumParameter,
    SettableEnumParameter,
    BinaryParameter,
    SettableAndQueryableToggleParameter,
    int_to_enum,
    SettableAndQueryableBinaryParameter,
    SettableBinaryParameter,
    CompositeParameter,
)
from pyziggy.mqtt_client import MqttClientImpl

from pyziggy.device_bases import *

"""
        )
    )

    cg = ClassGenerator()

    available_devices: List[CodeLine] = [
        CodeLine("class AvailableDevices(DevicesClient):", CodeIndent.INDENT),
        CodeLine("def __init__(self, impl: MqttClientImpl | None = None):", CodeIndent.INDENT),
        CodeLine("super().__init__(impl)"),
    ]

    for device_description in payload:
        device = DeviceDefinition.extract(device_description)

        if device is None:
            continue

        init_lines: List[CodeLine] = [
            CodeLine("def __init__(self, name):", CodeIndent.INDENT)
        ]
        base_class_names: List[str] = []

        for base_template in device_base_rules:
            matched_parameters = base_template.match(device.parameters)

            if matched_parameters is None:
                continue

            device.parameters = [
                p for p in device.parameters if p not in matched_parameters
            ]
            base_cls = generate_class_skeleton(cg, matched_parameters)
            base_class_names += [base_template.name]
            base_args = ["self"]
            init_lines += [
                CodeLine(
                    f"{base_template.name}.__init__({', '.join(base_args + base_cls.get_init_arg_values())})"
                )
            ]

        cls = generate_class_skeleton(cg, device.parameters)
        init_lines += cls.get_init()

        init_lines += [
            CodeLine("Device.__init__(self, name)", CodeIndent.UNINDENT),
            CodeLine(""),
        ]

        device_class_name = cg.generate_class(
            f"{sanitize_for_type_name(device.vendor)}_{sanitize_for_type_name(device.model_id)}",
            init_lines,
            ["Device"] + base_class_names,
            avoid_duplicate_class_impls=True,
        )

        device_property_name = f"{sanitize_for_property_name(device.friendly_name)}"

        available_devices += [
            CodeLine(
                f'self.{device_property_name} = {device_class_name}("{device.friendly_name}")'
            )
        ]

    available_devices += [CodeLine("", CodeIndent.UNINDENT2)]

    code += cg._enum_class_generator.get_code_for_enum_class_definitions()
    code += cg._enum_parameter_generator.get_code_for_enum_parameter_definitions()

    generated_classes = dict(sorted(cg.get_generated_classes().items()))

    for class_name, class_code in generated_classes.items():
        if not "CompositeParameter" in class_name:
            continue

        code += class_code

    for class_name, class_code in generated_classes.items():
        if "CompositeParameter" in class_name:
            continue

        code += class_code

    code += available_devices

    with open(output.parent / "__init__.py", "w") as f:
        f.write("")

    with open(output, "w") as f:
        f.write(CodeLine.join("\n", code))


def generate_device_bases():
    def generate_class(generator: ClassGenerator, class_req: BaseClassRequirement):
        skeleton = ClassSkeleton(generator)

        base_classes = [
            base_class
            for base_class in class_req.reqs
            if isinstance(base_class, BaseClassRequirement)
        ]
        for base_class in base_classes:
            base_skeleton = generate_class(generator, base_class)
            skeleton.add_entry(
                ClassSkeletonEntry(
                    None,
                    f"{base_class.name}.__init__(self, $args)",
                    base_skeleton.get_init_args(),
                )
            )

        params = [
            param
            for param in class_req.reqs
            if isinstance(param, ParameterBaseDefinition)
        ]
        skeleton.append(generate_class_skeleton(generator, params))

        init_args = ["self"]

        with ScopedCounter() as _:
            init_args += skeleton.get_init_arg_values()

        with ScopedCounter() as _:
            cg.generate_class(
                class_req.name,
                [
                    CodeLine(
                        f"def __init__({', '.join(init_args)}):",
                        CodeIndent.INDENT,
                    )
                ]
                + skeleton.get_init()
                + [CodeLine("", CodeIndent.UNINDENT2)],
                base_class_names=[b.name for b in base_classes],
            )

        return skeleton

    cg = ClassGenerator()

    for base_class in device_base_rules:
        generate_class(cg, base_class)

    code = """# This file is autogenerated by pyziggy
# See pyziggy.generator.generate_device_bases()

from pyziggy.parameters import (
    NumericParameter,
    QueryableNumericParameter,
    SettableAndQueryableNumericParameter,
    EnumParameter,
    SettableEnumParameter,
    BinaryParameter,
    SettableToggleParameter,
    SettableAndQueryableToggleParameter,
    CompositeParameter,
    int_to_enum,
)

"""

    for class_name, class_code in cg.get_generated_classes().items():
        code += CodeLine.join("\n", class_code)

    all_imports: List[CodeLine] = [CodeLine("__all__ = [", CodeIndent.INDENT)]

    for b in device_base_rules:
        if isinstance(b, BaseClassRequirement):
            all_imports += [CodeLine(f"'{b.name}',")]

    all_imports += [CodeLine("]", CodeIndent.UNINDENT)]

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
