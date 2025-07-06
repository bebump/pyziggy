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

from abc import abstractmethod
from bisect import bisect_left
from enum import IntEnum
from typing import List, Tuple, Callable, Any, override, final

from ..device_bases import LightWithDimming
from ..devices_client import DevicesClient
from ..message_loop import MessageLoopTimer, message_loop


def map_linear(value: float, low: float, high: float) -> float:
    """
    Maps a value from the range [0, 1] to the range [low, high].
    """
    return low + (high - low) * value


def clamp(value: float, low: float, high: float) -> float:
    """
    Clamps a value to the range [low, high].
    """
    return max(low, min(value, high))


class Barriers:
    class _Direction(IntEnum):
        NONE = 0
        UP = 1
        DOWN = 2

    @staticmethod
    def _get_allowed_direction(direction: Barriers._Direction) -> Barriers._Direction:
        if direction == Barriers._Direction.UP:
            return Barriers._Direction.DOWN
        elif direction == Barriers._Direction.DOWN:
            return Barriers._Direction.UP
        return Barriers._Direction.NONE

    def __init__(
        self, barriers: list[float], limit_callback: Callable[[], None] = lambda: None
    ):
        self._barriers: list[float] = barriers
        self._activated_barrier: int | None = None
        self._activated_by: Barriers._Direction = Barriers._Direction.NONE
        self._last_value: float | None = None
        self._last_barrier: int | None = None
        self._timer = MessageLoopTimer(self._reset)
        self._barrier_activation_callback: Callable[[], None] = limit_callback

        self._barriers.sort()

    def _reset(self, timer: MessageLoopTimer):
        timer.stop()
        self._activated_barrier = None

    def _set_last_value(self, value: float) -> float:
        self._last_value = value
        return value

    def apply(self, value: float):
        if self._last_value is None:
            return self._set_last_value(value)

        direction = (
            Barriers._Direction.UP
            if value > self._last_value
            else Barriers._Direction.DOWN
        )

        if self._activated_barrier is not None:
            if self._activated_by == direction:
                return self._set_last_value(self._barriers[self._activated_barrier])

        if self._activated_by == direction:
            self._activated_by = Barriers._Direction.NONE

        if self._last_barrier is None:
            self._last_barrier = bisect_left(self._barriers, self._last_value)

        barrier = bisect_left(self._barriers, value)

        def compute_barrier_to_activate() -> int:
            if self._last_barrier == barrier:
                return -1

            def get_offset(delta: int) -> int:
                return delta if delta < 0 else delta - 1

            # We are allowed to move beyond 1 barrier unobstructed if it's in the allowed direction
            num_allowed_barriers = (
                2
                if direction == Barriers._get_allowed_direction(self._activated_by)
                else 1
            )

            assert self._last_barrier is not None

            if abs(barrier - self._last_barrier) < num_allowed_barriers:
                return -1

            delta = int(
                clamp(
                    barrier - self._last_barrier,
                    -num_allowed_barriers,
                    num_allowed_barriers,
                )
            )

            return self._last_barrier + get_offset(delta)

        barrier_to_activate = compute_barrier_to_activate()

        self._last_value = value

        if self._last_barrier != barrier:
            self._activated_by = Barriers._Direction.NONE

        self._last_barrier = barrier

        if 0 <= barrier_to_activate < len(self._barriers):
            self._timer.start(0.75)
            self._activated_barrier = barrier_to_activate
            self._last_barrier = self._activated_barrier + (
                1 if direction == Barriers._Direction.UP else 0
            )
            self._activated_by = direction
            self._barrier_activation_callback()
            return self._set_last_value(self._barriers[barrier_to_activate])

        return self._set_last_value(value)


class Scalable:
    @abstractmethod
    def set_normalized(self, value: float):
        pass

    @abstractmethod
    def get_normalized(self) -> float:
        pass


class LightWithDimmingScalable(Scalable):
    def __init__(self, light: LightWithDimming):
        self._light = light

    @override
    def set_normalized(self, value: float):
        self._light.brightness.set_normalized(value)

        if value > 0:
            self._light.state.set(1)
        else:
            self._light.state.set(0)

    @override
    def get_normalized(self) -> float:
        return (
            self._light.brightness.get_normalized()
            if self._light.state.get() > 0
            else 0
        )


class ScaleMapper:
    class _MockScalable(Scalable):
        def __init__(self):
            self.value = 0.0

        @override
        def set_normalized(self, value):
            self.value = clamp(value, 0, 1)

        @override
        def get_normalized(self):
            return self.value

    def __init__(
        self,
        adjustables: List[Tuple[Scalable, float, float]],
        barriers: list[float] = [],
        barrier_activation_callback: Callable[[], Any] = lambda: None,
    ):
        super().__init__()
        self._adjustables: List[Tuple[Scalable, float, float]] = []
        self._barrier_callback = barrier_activation_callback
        self._barriers = Barriers(barriers, self._barrier_callback)

        for elem in adjustables:
            self._adjustables.append((elem[0], elem[1], elem[2]))

        self._adjustables.sort(key=lambda x: x[1])

        x = self._adjustables[0][1] if self._adjustables else 0.0

        # This is to allow non-contiguous ranges
        fake_lights: List[Tuple[Scalable, float, float]] = []

        for adjustable in self._adjustables:
            if x < adjustable[1]:
                fake_lights.append((ScaleMapper._MockScalable(), x, adjustable[1]))
            x = adjustable[2]

        self._adjustables.extend(fake_lights)

    @staticmethod
    def get_value_on_scale(
        adjustable: Tuple[Scalable, float, float],
        increment: float,
    ):
        value = adjustable[0].get_normalized()
        low = adjustable[1]
        high = adjustable[2]

        if value == 0.0:
            return 0.0 if increment < 0 else low
        if value == 1.0:
            return 1.0 if increment > 0 else high

        return map_linear(value, low, high)

    @staticmethod
    def get_value_for_scale(
        adjustable: Tuple[Scalable, float, float],
        scale_value: float,
    ):
        low = adjustable[1]
        high = adjustable[2]

        n = scale_value - low
        d = high - low

        if d == 0:
            return 0.0 if n < 0 else 1.0

        return clamp(n / d, 0, 1)

    def add(self, increment: float):
        values_on_scale = [
            ScaleMapper.get_value_on_scale(adjustable, increment)
            for adjustable in self._adjustables
        ]

        if not values_on_scale:
            return

        scale_value = min(values_on_scale) if increment > 0 else max(values_on_scale)
        scale_value = clamp(scale_value + increment, 0, 1)
        limited_scale_value = self._barriers.apply(scale_value)

        scale_value = limited_scale_value

        for adjustable in self._adjustables:
            new_value = ScaleMapper.get_value_for_scale(adjustable, scale_value)
            adjustable[0].set_normalized(new_value)


class RunThenExit:
    def __init__(self, devices: DevicesClient, callback: Callable[[], Any]):
        self._callback = callback
        self._timer = MessageLoopTimer(self._run)
        self._callback_count = 0

        devices.on_connect.add_listener(lambda: self._timer.start(1))

    def _run(self, timer: MessageLoopTimer):
        if self._callback_count == 0:
            self._callback()

        elif self._callback_count == 1:
            timer.stop()
            message_loop.stop()

        self._callback_count += 1


class TimedRunner:
    """
    Inherit from this class and override the run method to have a one-shot
    timed script encapsulating a DevicesClient.

    The TimedRunner will run all commands at the right time and after the
    last it will call message_loop.stop().

    Example:
        class Test(TimedRunner):
            @override
            def run(self):
                if self.wait(2):
                    devices.tokabo.brightness.set_normalized(1)
                    devices.tokabo.color_temp.set(454)

                if self.wait(1):
                    devices.tokabo.state.set(1)

                if self.wait(1):
                    devices.tokabo.state.set(0)

                if self.wait(1):
                    devices.tokabo.color_temp.set(179)

                if self.wait(1):
                    devices.tokabo.state.set(1)

                if self.wait(1):
                    devices.tokabo.color_temp.set(255)

                if self.wait(1):
                    devices.tokabo.brightness.query_device()

        _ = Test(devices)
        devices._loop_forever()
    """

    def __init__(self, client: DevicesClient):
        self._timer = MessageLoopTimer(self._timer_callback)
        self._wait_id_to_run = -1
        self._wait_id = 0
        self._can_run = True
        self._next_wait_interval: float = 0
        self._quit_now = False
        self.stop_message_loop_when_done = True

        client.on_connect.add_listener(self._setup_next_callback)

    def set_stop_message_loop_when_done(self, stop: bool):
        """
        Set whether to stop the message loop when done. The default value is True.
        """
        self.stop_message_loop_when_done = stop

    @abstractmethod
    def run(self):
        pass

    @final
    def wait(self, seconds):
        activated = self._wait_id == self._wait_id_to_run
        self._wait_id += 1

        if not activated:
            return False

        self._next_wait_interval = seconds

        return self._can_run

    def _setup_next_callback(self):
        self._wait_id_to_run += 1

        self._can_run = False
        self._wait_id = 0
        self.run()

        if self._wait_id <= self._wait_id_to_run:
            self._next_wait_interval = 0.5
            self._quit_now = True

        self._timer.start(self._next_wait_interval)

    def _timer_callback(self, timer: MessageLoopTimer):
        timer.stop()

        if self._quit_now:
            if self.stop_message_loop_when_done:
                message_loop.stop()

            return

        self._can_run = True
        self._wait_id = 0
        self.run()

        self._setup_next_callback()
