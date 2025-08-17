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

import datetime
import threading
import time
from abc import abstractmethod
from threading import Timer
from typing import Callable, Dict, Any, final

from .broadcasters import Broadcaster


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
        self.on_stop = Broadcaster()
        self._condition = threading.Condition()
        self._loop_should_quit: bool = False
        self._messages = []

    def _process_messages(self):
        while self._messages:
            m = self._messages.pop(0)
            m()

    def run(self):
        """
        Enters an infinite loop processing and dispatching messages. To exit
        the loop call stop().

        A minimal self-contained example of this is as follows::

            from pyziggy import message_loop as ml

            def start():
                mt.message_loop.stop()

            ml.message_loop.post_message(start)
            ml.message_loop.run()
        """
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
        self.on_stop._call_listeners()

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


class AsyncCallback(AsyncUpdater):
    def __init__(self, callback: Callable[[], None]):
        self._callback = callback

    def trigger_async_update(self):
        self._trigger_async_update()

    @final
    def _handle_async_update(self):
        self._callback()


message_loop = MessageLoop()


class TimeSource:
    @abstractmethod
    def perf_counter(self) -> float:
        pass

    @abstractmethod
    def time(self) -> float:
        pass

    @abstractmethod
    def now(self) -> datetime.datetime:
        pass


class SystemTimeSource(TimeSource):
    @final
    def perf_counter(self) -> float:
        return time.perf_counter()

    @final
    def time(self) -> float:
        return time.time()

    @final
    def now(self) -> datetime.datetime:
        return datetime.datetime.now()


class FastForwardTimeSource(TimeSource):
    def __init__(self):
        self._ahead_by: float = 0

    def fast_forward_by(self, seconds: float):
        self._ahead_by += seconds

    @final
    def perf_counter(self) -> float:
        return time.perf_counter() + self._ahead_by

    @final
    def time(self) -> float:
        return time.time() + self._ahead_by

    @final
    def now(self) -> datetime.datetime:
        return datetime.datetime.now() + datetime.timedelta(seconds=self._ahead_by)


time_source: TimeSource = SystemTimeSource()


class MessageLoopTimer:
    """
    AmazeTimer objects should only be created, started and stopped on the
    message thread.
    """

    _running_timers: list[MessageLoopTimer] = []
    _stopped_timers: list[MessageLoopTimer] = []
    _last_advance_time = time_source.perf_counter()
    _timer = Timer(1, lambda: MessageLoopTimer._timer_thread_callback())
    _async_callback = AsyncCallback(
        lambda: MessageLoopTimer._message_callback_dispatch()
    )
    _dispatch_counter: int = 0

    def __init__(self, callback: Callable[[MessageLoopTimer], None]):
        self._duration: float = 0
        self._wait_time: float = 0
        self._should_stop = False
        self._in_running_timers = False
        self._callback = callback

    def start(self, duration: float):
        self._should_stop = False
        self._duration = duration
        self._wait_time = duration

        MessageLoopTimer._advance_timers()

        if not self._in_running_timers:
            MessageLoopTimer._running_timers.append(self)
            self._in_running_timers = True

        MessageLoopTimer._reshuffle_timers()
        MessageLoopTimer._update_timer_thread()

    def stop(self):
        self._should_stop = True

    def _timer_callback(self):
        if not self._should_stop:
            self._callback(self)

    @classmethod
    def get_time_source(cls) -> TimeSource:
        """
        Returns the current time source used by the message loop timers.
        """
        return time_source

    @classmethod
    def _reshuffle_timers(cls):
        new_timers = []

        for t in cls._running_timers:
            if t._should_stop:
                t._in_running_timers = False
                continue

            new_timers.append(t)

        cls._running_timers = new_timers
        cls._running_timers = sorted(cls._running_timers, key=lambda t: t._wait_time)

    @classmethod
    def _advance_timers(cls):
        now = time_source.perf_counter()
        elapsed = now - cls._last_advance_time
        cls._last_advance_time = now

        for timer in cls._running_timers:
            timer._wait_time -= elapsed

    @classmethod
    def _timer_thread_callback(cls):
        cls._async_callback.trigger_async_update()

    @classmethod
    def _update_timer_thread(cls):
        if not cls._running_timers:
            cls._timer.cancel()
            return

        time_until_next_callback = cls._running_timers[0]._wait_time

        def clamp(value: float, low: float, high: float) -> float:
            return max(low, min(value, high))

        time_until_next_callback = clamp(time_until_next_callback, 0.001, 0.5)

        if isinstance(time_source, FastForwardTimeSource):
            time_source.fast_forward_by(time_until_next_callback + 0.001)
            cls._timer_thread_callback()
        else:
            cls._timer = Timer(
                clamp(time_until_next_callback, 0.001, 0.5), cls._timer_thread_callback
            )
            cls._timer.start()

    @classmethod
    def _message_callback_dispatch(cls):
        if isinstance(time_source, FastForwardTimeSource):
            if cls._dispatch_counter % 10 == 0:
                cls._message_callback()
            else:
                cls._async_callback.trigger_async_update()

            cls._dispatch_counter += 1
            return

        cls._message_callback()

    @classmethod
    def _message_callback(cls):
        cls._advance_timers()
        callback_start = time_source.perf_counter()

        while time_source.perf_counter() - callback_start < 0.1:
            if not cls._running_timers:
                break

            timer = cls._running_timers[0]

            if timer._wait_time > 0:
                break

            timer._timer_callback()
            timer._wait_time = timer._duration
            cls._reshuffle_timers()
            cls._advance_timers()

        cls._update_timer_thread()
