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

from typing import List

from ..parser import (
    ParameterBaseDefinition,
)


class BaseClassRequirement:
    def __init__(
        self, name: str, reqs: List[BaseClassRequirement | ParameterRequirement]
    ):
        self.name = name
        self.reqs = reqs

    def get_actualized(self, parameters: List[ParameterBaseDefinition]) -> BaseClassRequirement | None:
        consumable_parameters = parameters.copy()
        actualized_reqs = self.reqs.copy()

        for i in range(0, len(actualized_reqs)):
            actualized_req = actualized_reqs[i].get_actualized(consumable_parameters)

            if actualized_req is None:
                return None

            actualized_reqs[i] = actualized_req

        parameters[:] = consumable_parameters[:]
        return BaseClassRequirement(self.name, actualized_reqs)


class ParameterRequirement:
    def __init__(self, parameter: ParameterBaseDefinition):
        self.parameter: ParameterBaseDefinition = parameter

    def get_actualized(self, parameters: List[ParameterBaseDefinition]) -> ParameterRequirement | None:
        matching_param: int | None = None

        for i, param in enumerate(parameters):
            if self.parameter.is_match_for(param):
                matching_param = i
                break

        if matching_param is None:
            return None

        result = ParameterRequirement(parameters[matching_param])
        del parameters[matching_param]
        return result
