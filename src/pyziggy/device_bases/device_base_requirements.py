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

from ..parser import (
    ParameterBaseDefinition,
)


class BaseClassRequirement:
    def __init__(
        self, name: str, reqs: List[BaseClassRequirement | ParameterBaseDefinition]
    ):
        self.name = name
        self.reqs = reqs

    def match(
        self,
        parameters: List[ParameterBaseDefinition],
        matching_parameters: List[ParameterBaseDefinition] | None = None,
    ) -> List[ParameterBaseDefinition] | None:
        if matching_parameters is None:
            matching_parameters = []

        for req in self.reqs:
            if isinstance(req, BaseClassRequirement):
                result = req.match(parameters, matching_parameters)

                if result is None:
                    return None

                matching_parameters += [r for r in result if r not in matching_parameters]
            elif isinstance(req, ParameterBaseDefinition):
                match_found = False

                for param in parameters:
                    if param not in matching_parameters and req.is_match_for(param):
                        matching_parameters.append(param)
                        match_found = True
                        break

                if not match_found:
                    return None

        return matching_parameters
