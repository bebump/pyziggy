from emkyoot.message_loop import MessageLoopTimer
from emkyoot.parameters import Broadcaster, AnyBroadcaster
from emkyoot_autogenerate.available_devices import (
    IKEA_Remote_Control_N2,
    Philips_RDM002,
)


class RepeatingActionBroadcaster:
    def __init__(self, action, repeating_values):
        self.repeating_action: Broadcaster = Broadcaster()
        self._action = action
        self._repeating_values = repeating_values
        self._timer = MessageLoopTimer(self._timer_callback)

        self._action.add_listener(self._action_listener)

    def _action_listener(self):
        self._timer_callback(self._timer)

        action_value = self._action.get_enum_value()

        if action_value in self._repeating_values:
            self._timer.start(0.5)
        else:
            self._timer.stop()

    def _timer_callback(self, timer: MessageLoopTimer):
        self.repeating_action._call_listeners()


class IkeaN2CommandRepeater(RepeatingActionBroadcaster):
    """
    When a button is held, the IkeaN2 will emit a pair of events such as
    arrow_left_hold and then arrow_left_release. This class intercepts such
    command pairs and keeps repeatedly calling the action broadcaster until
    the button is released.
    """

    def __init__(self, remote: IKEA_Remote_Control_N2):
        t = remote.action.enum_type
        super().__init__(
            remote.action,
            [
                t.brightness_move_up,
                t.brightness_move_down,
                t.arrow_left_hold,
                t.arrow_right_hold,
            ],
        )


class PhilipsTapDialRotaryHelper:
    def __init__(self, remote: Philips_RDM002):
        remote.action.set_use_synchronous_broadcast(True)

        self.on_rotate = AnyBroadcaster()
        self._remote = remote
        self._remote.action.add_listener(self._on_action)
        self._suppress_step_255: bool = False
        self._step_255_suppression_timer: MessageLoopTimer = MessageLoopTimer(
            self._stop_suppress_step_255
        )

    def _start_suppress_step_255(self):
        self._suppress_step_255 = True
        self._step_255_suppression_timer.start(1)

    def _stop_suppress_step_255(self, timer: MessageLoopTimer):
        self._suppress_step_255 = False
        timer.stop()

    def _on_action(self):
        t = self._remote.action.enum_type
        action = self._remote.action.get_enum_value()
        step = self._remote.action_step_size.get()

        # Holding down button 1 will also emit a brightness_step_up action with
        # step size 255. AFAICT there's no other way to tell that event apart
        # from a legitimate dial rotation
        if step == 255 and self._suppress_step_255:
            return

        if action == t.brightness_step_up:
            self.on_rotate._call_listeners(lambda l: l(step))
        elif action == t.brightness_step_down:
            self.on_rotate._call_listeners(lambda l: l(-step))
        elif (
            action == t.button_1_press
            or action == t.button_2_press
            or action == t.button_3_press
            or action == t.button_4_press
        ):
            self._start_suppress_step_255()
