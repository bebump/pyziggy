from __future__ import annotations

from abc import abstractmethod
from bisect import bisect_left
from enum import IntEnum
from typing import List, Tuple, Callable, Any, override

from emkyoot.device_bases import LightWithDimming
from emkyoot.message_loop import MessageLoopTimer


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


if __name__ == "__main__":
    from emkyoot.message_loop import MessageLoopTimer

    timer = MessageLoopTimer(lambda x: None)

    b = Barriers([0.2, 0.5, 0.8])

    def reset_timer():
        print("reset")
        b._reset(timer)

    def apply_value(val):
        return b.apply(val)

    assert apply_value(0.1) == 0.1
    assert apply_value(0.3) == 0.2
    reset_timer()
    assert apply_value(0.6) == 0.5
    assert apply_value(0.0) == 0.2
    assert apply_value(1.0) == 0.5
    reset_timer()
    assert apply_value(0.75) == 0.75
    assert apply_value(0.48) == 0.5
    reset_timer()
    assert apply_value(0.4) == 0.4
    apply_value(0.51)
    reset_timer()
    apply_value(0.0)
    reset_timer()
    apply_value(0.0)
    apply_value(0.25)
    reset_timer()
    apply_value(0.52)
    reset_timer()
    apply_value(0.1)

    b = Barriers([0.55, 0.94])
    assert apply_value(0) == 0
    assert apply_value(0.6) == 0.55
    reset_timer()
    assert apply_value(0.96) == 0.94
    reset_timer()
    assert apply_value(0.83) == 0.83
    assert apply_value(0.2) == 0.55
