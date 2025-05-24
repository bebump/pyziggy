from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any


class MessageEvent:
    def __init__(
        self, incoming: bool, time: float, topic: str, payload: Dict[str, Any]
    ):
        self.incoming = incoming
        self.topic = topic
        self.payload = payload
        self.time = time

    def __eq__(self, other):
        if not isinstance(other, MessageEvent):
            return False

        return (
            self.incoming == other.incoming
            and self.topic == other.topic
            and self.payload == other.payload
            and self.time == other.time
        )

    def __repr__(self):
        time_string = f"{self.time:.2f}"
        indented_time_string = " " * max(6 - len(time_string), 0) + time_string

        recv_or_send = "RECV" if self.incoming else "SEND"
        line = f"{indented_time_string}  {recv_or_send}  {self.topic}  "

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
        if self.topic != other.topic:
            return False

        if self.incoming != other.incoming:
            return False

        if self.time > other.time:
            return False

        return self._payload_satisfied_by(self.payload, other.payload)

    @staticmethod
    def from_str(s: str) -> list[MessageEvent]:
        import re

        first_line_pattern = r"^\s*(\d+\.\d+)  (RECV|SEND)  (.+)\s+{"

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
                    incoming = dir_str == "RECV"
                    topic = topic_str.strip()
                    bracket_count = 1

                    payload_str = "{"
                    event_found = True
            else:
                payload_str += line.strip()
                bracket_count += line.count("{")
                bracket_count -= line.count("}")

                if bracket_count == 0:
                    events.append(
                        MessageEvent(incoming, t, topic, json.loads(payload_str))
                    )
                    event_found = False

        return events

    @staticmethod
    def dumps(events: list[MessageEvent], file: Path):
        result = ""

        for event in events:
            result += str(event)
            result += "\n" + "-" * 110 + "\n"

    @staticmethod
    def loads(s: str):
        return MessageEvent.from_str(s)

    @staticmethod
    def dump(events: list[MessageEvent], file: Path):
        with open(file, "w") as f:
            f.write(MessageEvent.dumps(events, file))

    @staticmethod
    def load(file: Path):
        with open(file, "r") as f:
            return MessageEvent.loads(f.read())
