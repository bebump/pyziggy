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

from typing import Tuple

from . import MessageEvent


class MessageEventsWithLocations:
    def __init__(self, events: list[MessageEvent]):
        self.events = events
        self.line_ranges: list[Tuple[int, int]] = []
        self.max_line_length = 0
        self.lines: list[str] = []

        for e in self.events:
            chunk = MessageEvent.dumps([e])
            last_line_range_end = self.line_ranges[-1][1] if self.line_ranges else 0
            start = (
                last_line_range_end
                if last_line_range_end == 0
                else last_line_range_end + 1
            )

            num_lines = 0

            for line in chunk.splitlines():
                self.max_line_length = max(self.max_line_length, len(line))
                self.lines.append(line)
                num_lines += 1

            end = start + num_lines - 1
            self.line_ranges.append((start, end))

    def get_padded_events_string(self, pad_left: bool = True, vertical_delimiter="|"):
        string = ""

        for line in self.lines:
            if pad_left:
                string += vertical_delimiter + line + "\n"
            else:
                padding_length = self.max_line_length - len(line)
                string += line + " " * padding_length + vertical_delimiter + "\n"

        return string


def create_ascii_art_connecting_rows(
    left_row: int, right_row: int, width: int, line_char: str = "*"
):
    """
    Copilot generated this entire function correctly on the first try.

    Draw an ASCII art line connecting the left side of one row to the right side of another row.

    Args:
        left_row: Row index for the left endpoint (0-based)
        right_row: Row index for the right endpoint (0-based)
        width: Width of the drawing area
        line_char: Character to use for drawing the line

    Returns:
        List of strings representing the ASCII art
    """
    # Calculate height needed for the drawing
    height = max(left_row, right_row) + 1

    # Create a matrix filled with spaces
    matrix = [[" " for _ in range(width)] for _ in range(height)]

    # Define the start and end points
    x0, y0 = 0, left_row
    x1, y1 = width - 1, right_row

    # Bresenham's line algorithm
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy

    while True:
        if 0 <= y0 < height and 0 <= x0 < width:
            matrix[y0][x0] = line_char

        if x0 == x1 and y0 == y1:
            break

        e2 = 2 * err
        if e2 >= dy:
            if x0 == x1:
                break
            err += dy
            x0 += sx

        if e2 <= dx:
            if y0 == y1:
                break
            err += dx
            y0 += sy

    return "\n".join(["".join(row) for row in matrix])


def create_union_of_connection_ascii_arts(a: str, b: str, line_char: str = "*") -> str:
    """
    Copilot generated this entire function correctly for the first try.

    Merge two ASCII art strings, preserving all line characters from both inputs.

    Args:
        a: First ASCII art string
        b: Second ASCII art string
        line_char: Character used for drawing lines

    Returns:
        String with merged ASCII art
    """
    # Split both strings into lines
    a_lines = a.splitlines()
    b_lines = b.splitlines()

    # Determine the maximum number of lines
    max_lines = max(len(a_lines), len(b_lines))

    # Pad both lists to the same length
    a_lines = a_lines + [""] * (max_lines - len(a_lines))
    b_lines = b_lines + [""] * (max_lines - len(b_lines))

    # Merge the lines
    result_lines = []
    for a_line, b_line in zip(a_lines, b_lines):
        # Determine the length of the merged line
        merged_length = max(len(a_line), len(b_line))

        # Create a new line with spaces
        merged_line = [" "] * merged_length

        # Fill with characters from line a
        for i, char in enumerate(a_line):
            if char == line_char:
                merged_line[i] = line_char

        # Fill with characters from line b
        for i, char in enumerate(b_line):
            if char == line_char:
                merged_line[i] = line_char

        result_lines.append("".join(merged_line))

    return "\n".join(result_lines)


def create_connection_ascii_art(
    events1: list[MessageEvent],
    events2: list[MessageEvent],
    connections: list[Tuple[int, int]],
) -> str:
    e1 = MessageEventsWithLocations(events1)
    e2 = MessageEventsWithLocations(events2)

    row_connections: list[Tuple[int, int]] = []

    for c in connections:
        r1 = e1.line_ranges[c[0]]
        r2 = e2.line_ranges[c[1]]
        row_connections.append(
            (r1[0] + (r1[1] - r1[0]) // 2, r2[0] + (r2[1] - r2[0]) // 2)
        )

    connections_string = ""

    for left, right in row_connections:
        ascii_art = create_ascii_art_connecting_rows(left, right, 40)
        connections_string = create_union_of_connection_ascii_arts(
            connections_string, ascii_art
        )

    e1_lines = e1.get_padded_events_string(pad_left=False).splitlines()
    e2_lines = e2.get_padded_events_string(pad_left=True).splitlines()
    connections_lines = connections_string.splitlines()

    result = ""

    for i in range(max(len(e1_lines), len(e2_lines), len(connections_lines))):
        e1_line = e1_lines[i] if i < len(e1_lines) else " " * (e1.max_line_length + 1)
        e2_line = e2_lines[i] if i < len(e2_lines) else " " * e2.max_line_length
        connection_line = (
            connections_lines[i] if i < len(connections_lines) else " " * 40
        )

        result += f"{e1_line}{connection_line}{e2_line}\n"

    return result
