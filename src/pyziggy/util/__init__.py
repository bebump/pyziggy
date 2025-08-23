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

"""
Utility classes and functions that may come handy for building automations.
"""

from ._util import Barriers as Barriers
from ._util import Scalable as Scalable
from ._util import LightWithDimmingScalable as LightWithDimmingScalable
from ._util import ScaleMapper as ScaleMapper
from ._util import map_linear, clamp, LightWithDimmingScalable, RunThenExit, TimedRunner

__all__ = [
    "map_linear",
    "clamp",
    "Scalable",
    "ScaleMapper",
    "LightWithDimmingScalable",
    "RunThenExit",
    "TimedRunner",
]
