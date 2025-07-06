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

from enum import IntEnum
from typing import List


class CodeIndent(IntEnum):
    NONE = 0
    INDENT = 1
    UNINDENT = 2
    UNINDENT2 = 3


class CodeLine:
    def __init__(
        self,
        line: str = "",
        postindent: CodeIndent = CodeIndent.NONE,
    ):
        assert isinstance(line, str)
        self.line = line
        self.postindent = postindent

    def __eq__(self, other):
        if not isinstance(other, CodeLine):
            return False
        return (
            self.line == other.line
            and self.postindent == other.postindent
        )

    def __str__(self):
        return self.line

    @staticmethod
    def join(separator: str, lines: List[CodeLine]) -> str:
        result = ""
        indent_level = 0

        for line in lines:
            if indent_level < 0:
                indent_level = 0

            new_line = "    " * indent_level + str(line)

            if new_line.strip() == "":
                new_line = new_line.replace(" ", "")

            result += new_line + separator

            if line.postindent == CodeIndent.INDENT:
                indent_level += 1
            elif line.postindent == CodeIndent.UNINDENT:
                indent_level -= 1
            elif line.postindent == CodeIndent.UNINDENT2:
                indent_level -= 2

        return result
