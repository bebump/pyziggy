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

import threading
from abc import abstractmethod
from typing import Callable, Dict, Any, final


class Singleton(type):
    _instances: Dict[type, Any] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class AtomicInteger:
    def __init__(self, value: int = 0):
        self._value: int = value
        self._lock = threading.Lock()

    def get(self) -> int:
        self._lock.acquire()
        value = self._value
        self._lock.release()
        return value

    def set(self, new_value: int) -> None:
        self._lock.acquire()
        self._value = new_value
        self._lock.release()

    def get_and_set(self, new_value: int) -> int:
        self._lock.acquire()
        old_value = self._value
        self._value = new_value
        self._lock.release()
        return old_value


class MessageLoop(metaclass=Singleton):
    def __init__(self):
        self._condition = threading.Condition()
        self._loop_should_quit: bool = False
        self._messages = []

    def _process_messages(self):
        while self._messages:
            m = self._messages.pop(0)
            m()

    def rum(self):
        with self._condition:
            self._loop_should_quit = False
            while not self._loop_should_quit:
                self._condition.wait()
                self._process_messages()

    def run(self):
        self._loop_should_quit = False
        messages = []

        while True:
            with self._condition:
                if self._loop_should_quit:
                    return

                if not self._messages:
                    self._condition.wait()

                messages = self._messages
                self._messages = []

            while messages:
                m = messages.pop(0)
                m()

    def stop(self):
        with self._condition:
            self._loop_should_quit = True
            self._condition.notify()

    def post_message(self, message: Callable[[], None]):
        with self._condition:
            self._messages.append(message)
            self._condition.notify()


class AsyncUpdater:
    def __init__(self):
        pass

    @abstractmethod
    def _handle_async_update(self):
        """Override this method in a subclass to receive a callback on the message thread"""
        raise NotImplementedError("Subclasses must implement this method")

    @final
    def _trigger_async_update(self):
        message_loop = MessageLoop()
        message_loop.post_message(self._handle_async_update)


message_loop = MessageLoop()
