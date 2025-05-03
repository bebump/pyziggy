from typing import Dict, Callable, Any


class ListenerCancellationToken:
    def __init__(self, broadcaster, listener_id: int):
        self._broadcaster = broadcaster
        self._listener_id = listener_id

    def stop_listening(self):
        self._broadcaster._remove_listener(self._listener_id)


class Broadcaster:
    def __init__(self):
        self._listeners: Dict[int, Callable[[], None]] = {}

    def add_listener(self, callback: Callable[[], Any]) -> ListenerCancellationToken:
        listener_id = len(self._listeners)
        self._listeners[listener_id] = callback
        return ListenerCancellationToken(self, listener_id)

    def _call_listeners(self):
        for k, listener in self._listeners.items():
            listener()

    def _remove_listener(self, listener_id: int) -> None:
        del self._listeners[listener_id]


class AnyBroadcaster:
    def __init__(self):
        self._listeners: Dict[int, Any] = {}

    def add_listener(self, callback: Any) -> ListenerCancellationToken:
        listener_id = len(self._listeners)
        self._listeners[listener_id] = callback
        return ListenerCancellationToken(self, listener_id)

    def _call_listeners(self, callback: Callable[[Any], None]):
        for k, listener in self._listeners.items():
            callback(listener)

    def _remove_listener(self, listener_id: int) -> None:
        del self._listeners[listener_id]
