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

from typing import List

from .device_base_requirements import BaseClassRequirement
from ..parser import ParameterAccessType
from ..parser import ToggleParameterDefinition, NumericParameterDefinition, CompositeParameterDefinition

dimmable_light = BaseClassRequirement(
    "LightWithDimming",
    [
        ToggleParameterDefinition(
            "state",
            "state",
            ParameterAccessType.EXISTS
            | ParameterAccessType.SETTABLE
            | ParameterAccessType.QUERYABLE,
        ),
        NumericParameterDefinition(
            "brightness",
            "brightness",
            ParameterAccessType.EXISTS
            | ParameterAccessType.SETTABLE
            | ParameterAccessType.QUERYABLE,
            None,
            None,
        ),
    ],
)

light_with_color_temp = BaseClassRequirement(
    "LightWithColorTemp",
    [
        dimmable_light,
        NumericParameterDefinition(
            "color_temp",
            "color_temp",
            ParameterAccessType.EXISTS
            | ParameterAccessType.SETTABLE
            | ParameterAccessType.QUERYABLE,
            None,
            None,
        ),
    ],
)

color_light = BaseClassRequirement(
    "LightWithColor",
    [
        light_with_color_temp,
        CompositeParameterDefinition(
            "color",
            "color_xy",
            ParameterAccessType.EXISTS
            | ParameterAccessType.SETTABLE
            | ParameterAccessType.QUERYABLE,
            [
                NumericParameterDefinition(
                    "x",
                    "x",
                    ParameterAccessType.EXISTS
                    | ParameterAccessType.SETTABLE
                    | ParameterAccessType.QUERYABLE,
                    None,
                    None,
                ),
                NumericParameterDefinition(
                    "y",
                    "y",
                    ParameterAccessType.EXISTS
                    | ParameterAccessType.SETTABLE
                    | ParameterAccessType.QUERYABLE,
                    None,
                    None,
                ),
            ],
        ),
        CompositeParameterDefinition(
            "color",
            "color_hs",
            ParameterAccessType.EXISTS
            | ParameterAccessType.SETTABLE
            | ParameterAccessType.QUERYABLE,
            [
                NumericParameterDefinition(
                    "hue",
                    "hue",
                    ParameterAccessType.EXISTS
                    | ParameterAccessType.SETTABLE
                    | ParameterAccessType.QUERYABLE,
                    None,
                    None,
                ),
                NumericParameterDefinition(
                    "saturation",
                    "saturation",
                    ParameterAccessType.EXISTS
                    | ParameterAccessType.SETTABLE
                    | ParameterAccessType.QUERYABLE,
                    None,
                    None,
                ),
            ],
        ),
    ],
)

# Enumerate base rules in reverse order of priority. Matching an abstraction removes the
# required parameters, so lower priority abstractions using those same parameters will not
# be matched.
device_base_rules: List[BaseClassRequirement] = [
    color_light,
    light_with_color_temp,
    dimmable_light,
]
