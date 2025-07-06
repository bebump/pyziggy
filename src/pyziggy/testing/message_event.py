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

import json
from enum import IntEnum
from pathlib import Path
from typing import Dict, Any, Tuple


class MessageEventKind(IntEnum):
    RECV = 0
    SEND = 1
    EXPECTED_ORDERED = 2
    EXPECTED_UNORDERED = 3
    PROHIBITED = 4

    def to_string(self):
        if self == MessageEventKind.RECV:
            return "RECV"
        elif self == MessageEventKind.SEND:
            return "SEND"
        elif self == MessageEventKind.EXPECTED_ORDERED:
            return "EXPO"
        elif self == MessageEventKind.EXPECTED_UNORDERED:
            return "EXPU"

        return "PROH"

    @staticmethod
    def from_string(s: str) -> MessageEventKind:
        if s == "RECV":
            return MessageEventKind.RECV
        elif s == "SEND":
            return MessageEventKind.SEND
        elif s == "EXPO":
            return MessageEventKind.EXPECTED_ORDERED
        elif s == "EXPU":
            return MessageEventKind.EXPECTED_UNORDERED
        elif s == "PROH":
            return MessageEventKind.PROHIBITED

        raise ValueError(f"Unknown message event kind: {s}")


class MessageEvent:
    def __init__(
        self, kind: MessageEventKind, time: float, topic: str, payload: Dict[str, Any]
    ):
        self.kind = kind
        self.topic = topic
        self.payload = payload
        self.time = time

    def __eq__(self, other):
        if not isinstance(other, MessageEvent):
            return False

        return (
            self.kind == other.kind
            and self.topic == other.topic
            and self.payload == other.payload
            and self.time == other.time
        )

    def __repr__(self):
        time_string = f"{self.time:.2f}"
        indented_time_string = " " * max(6 - len(time_string), 0) + time_string

        line = f"{indented_time_string}  {self.kind.to_string()}  {self.topic}  "

        payload_indent = max(len(line), 50)
        first_payload_line_indent = max(payload_indent - len(line), 0)

        json_string = json.dumps(self.payload, indent=2)

        return (
            line
            + " " * first_payload_line_indent
            + ("\n" + " " * payload_indent).join(json_string.splitlines())
        )

    @staticmethod
    def _payload_satisfied_by(
        generic: Dict[Any, Any], concrete: Dict[Any, Any]
    ) -> bool:
        if "*" in generic:
            if not all(key in concrete for key in generic.keys() if key != "*"):
                return False
        else:
            if generic.keys() != concrete.keys():
                return False

        for key in generic.keys():
            if key == "*":
                continue

            value = generic[key]

            if value == "*":
                continue

            if not isinstance(value, dict):
                if value != concrete[key]:
                    return False
                continue

            if not MessageEvent._payload_satisfied_by(value, concrete[key]):
                return False

        return True

    def satisfied_by(self, other: MessageEvent) -> bool:
        """
        Returns True if this message equals the other. If this message contains wildcards, and the
        other message equals it other than the wildcards, it returns True.

        Only this message can contain wildcards.

        A wildcard is a "*" value for a given key or a "*" key with any value, which matches any
        number of key, value pairs with any content.
        """
        if self.topic != "*" and self.topic != other.topic:
            return False

        if self.kind == MessageEventKind.SEND or self.kind == MessageEventKind.RECV:
            if self.kind != other.kind:
                return False
        elif other.kind != MessageEventKind.SEND:
            return False

        return self._payload_satisfied_by(self.payload, other.payload)

    @staticmethod
    def from_str(s: str) -> list[MessageEvent]:
        import re

        first_line_pattern = r"^\s*(\d+\.\d+)  (RECV|SEND|EXPO|EXPU|PROH)  (.+)\s+{"

        t: float = 0
        incoming: bool = False
        topic: str = ""
        payload_str = ""

        event_found = False
        bracket_count = 0

        events: list[MessageEvent] = []

        for line in s.splitlines():
            if not event_found:
                m = re.match(first_line_pattern, line)

                if m is not None:
                    time_str, dir_str, topic_str = m.groups()
                    t = float(time_str)
                    kind = MessageEventKind.from_string(dir_str)
                    topic = topic_str.strip()
                    bracket_count = line.count("{") - line.count("}")

                    payload_str = "{" + line.split("{", 1)[1]
                    event_found = True
            else:
                payload_str += line.strip()
                bracket_count += line.count("{") - line.count("}")

            if event_found and bracket_count == 0:
                events.append(MessageEvent(kind, t, topic, json.loads(payload_str)))
                event_found = False

        return events

    @staticmethod
    def dumps(events: list[MessageEvent]):
        result = ""

        for event in events:
            result += str(event)
            result += "\n" + "-" * 110 + "\n"

        return result

    @staticmethod
    def loads(s: str):
        return MessageEvent.from_str(s)

    @staticmethod
    def dump(events: list[MessageEvent], file: Path):
        with open(file, "w") as f:
            f.write(MessageEvent.dumps(events))

    @staticmethod
    def load(file: Path):
        with open(file, "r") as f:
            return MessageEvent.loads(f.read())


class MessageEventList:
    def __init__(self, events: list[MessageEvent] | None = None):
        self.events: list[MessageEvent] = events if events is not None else []

    def add(self, event: MessageEvent):
        self.events.append(event)

    def __len__(self):
        return len(self.events)

    def get(self, index: int) -> MessageEvent:
        return self.events[index]

    def get_next_recv_index(self, prev: int = -1) -> int | None:
        next_recv_index = prev + 1

        while True:
            if next_recv_index >= len(self.events):
                return None

            if self.events[next_recv_index].kind == MessageEventKind.RECV:
                break

            next_recv_index += 1

        return next_recv_index

    def get_from_recv_up_to_recv(self, end: int) -> list[MessageEvent]:
        """
        end should be the index of a RECV message. This function will return all messages starting
        from (and not including) the previous RECV message up to and not including the specified
        RECV message.
        """

        def clamp(n: int) -> int:
            return min(max(0, n), len(self.events) - 1)

        i = clamp(end - 1)

        while True:
            if self.events[i].kind == MessageEventKind.RECV:
                i = clamp(i + 1)
                break

            if i == 0:
                break

            i = clamp(i - 1)

        return self.events[i:end]


def generate_match_diagram(
    expected: list[MessageEvent],
    actual: list[MessageEvent],
    connections: list[Tuple[int, int]],
):
    pass
