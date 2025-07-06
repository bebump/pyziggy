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

from typing import Callable, Any


class ListenerCancellationToken:
    def __init__(self, broadcaster, listener_id: int):
        self._broadcaster = broadcaster
        self._listener_id = listener_id

    def stop_listening(self):
        self._broadcaster._remove_listener(self._listener_id)


class Broadcaster:
    class Listener:
        def __init__(self, callback: Callable[[], Any], id: int, order: int):
            self._callback = callback
            self._id = id
            self._order = order

    def __init__(self):
        self._next_listener_id = 0
        self._listeners: list[Broadcaster.Listener] = []

    def _get_next_listener_id(self) -> int:
        listener_id = self._next_listener_id
        self._next_listener_id += 1
        return listener_id

    def add_listener(
        self, callback: Callable[[], Any], order: int = 100
    ) -> ListenerCancellationToken:
        """
        Order affects where the listener will be inserted relative to others. The minimum value of -1
        means the listener will be inserted in front of all others. The default value is 100. There
        is no maximum, other than whatever int can hold.
        """
        assert order >= -1

        listener_id = self._get_next_listener_id()
        listener = Broadcaster.Listener(callback, listener_id, order)

        for i, existing_listener in enumerate(self._listeners):
            if existing_listener._order >= order:
                self._listeners.insert(i, listener)
                break
        else:
            self._listeners.append(listener)

        return ListenerCancellationToken(self, listener_id)

    def _call_listeners(self):
        for listener in self._listeners:
            listener._callback()

    def _remove_listener(self, listener_id: int) -> None:
        for i, listener in enumerate(self._listeners):
            if listener._id == listener_id:
                del self._listeners[i]
                break
        else:
            raise ValueError(
                f"Listener with id {listener_id} not found. This shouldn't be possible, please report."
            )


class AnyBroadcaster:
    class Listener:
        def __init__(self, callback: Any, id: int, order: int):
            self._callback = callback
            self._id = id
            self._order = order

    def __init__(self):
        self._next_listener_id = 0
        self._listeners: list[AnyBroadcaster.Listener] = []

    def _get_next_listener_id(self) -> int:
        listener_id = self._next_listener_id
        self._next_listener_id += 1
        return listener_id

    def add_listener(
        self, callback: Any, order: int = 100
    ) -> ListenerCancellationToken:
        """
        Order affects where the listener will be inserted relative to others. The minimum value of -1
        means the listener will be inserted in front of all others. The default value is 100. There
        is no maximum, other than whatever int can hold.
        """
        assert order >= -1

        listener_id = self._get_next_listener_id()
        listener = AnyBroadcaster.Listener(callback, listener_id, order)

        for i, existing_listener in enumerate(self._listeners):
            if existing_listener._order > order:
                self._listeners.insert(i, listener)
                break
        else:
            self._listeners.append(listener)

        return ListenerCancellationToken(self, listener_id)

    def _call_listeners(self, callback: Callable[[Any], None]):
        for listener in self._listeners:
            callback(listener._callback)

    def _remove_listener(self, listener_id: int) -> None:
        for i, listener in enumerate(self._listeners):
            if listener._id == listener_id:
                del self._listeners[i]
                break
        else:
            raise ValueError(
                f"Listener with id {listener_id} not found. This shouldn't be possible, please report."
            )
