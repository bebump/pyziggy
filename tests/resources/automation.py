from device_wrappers import (
    IkeaN2CommandRepeater,
    PhilipsTapDialRotaryHelper,
)
from emkyoot.parameters import (
    SettableBinaryParameter,
    SettableToggleParameter,
    SettableAndQueryableBinaryParameter,
    SettableAndQueryableToggleParameter,
)
from emkyoot_autogenerate.available_devices import AvailableDevices, Device
from util import ScaleMapper

devices = AvailableDevices()

kitchen = ScaleMapper(
    [
        (devices.hue_lightstrip, 0.0, 0.54),
        (devices.dining_light_1, 0.56, 0.93),
        (devices.dining_light_2, 0.56, 0.93),
        (devices.kitchen_light, 0.95, 1.0),
    ],
    [0.55, 0.94],
    lambda: print("\a"),
)

living_room = ScaleMapper(
    [
        (devices.standing_lamp, 0.0, 0.7),
        (devices.couch, 0.2, 0.7),
        (devices.reading_lamp, 0.7, 1.0),
    ]
)


def ikea_remote_action_handler():
    action = devices.ikea_remote.action.get_enum_value()
    types = devices.ikea_remote.action.enum_type

    if action == types.brightness_move_up:
        kitchen.add(0.075)
    elif action == types.brightness_move_down:
        kitchen.add(-0.075)
    elif action == types.on:
        devices.dining_light_1.state.set(1)
        devices.dining_light_2.state.set(1)
    elif action == types.off:
        devices.dining_light_1.state.set(0)
        devices.dining_light_2.state.set(0)


ikea_remote_action_broadcaster = IkeaN2CommandRepeater(devices.ikea_remote)
ikea_remote_action_broadcaster.repeating_action.add_listener(ikea_remote_action_handler)

philips_rotary_target = living_room

rotary_helper = PhilipsTapDialRotaryHelper(devices.philips_switch)
rotary_helper.on_rotate.add_listener(
    lambda step: philips_rotary_target.add(step / 8 * 0.022)
)


device_params_turned_off: list | None = None


def turn_off_everything():
    global device_params_turned_off

    device_params_turned_off = []

    for name, device in vars(devices).items():
        if not isinstance(device, Device):
            continue

        for property, param in vars(device).items():
            if property == "state":
                if (
                    isinstance(param, SettableBinaryParameter)
                    or isinstance(param, SettableAndQueryableBinaryParameter)
                    or isinstance(param, SettableToggleParameter)
                    or isinstance(param, SettableAndQueryableToggleParameter)
                ):
                    if param.get() > 0:
                        device_params_turned_off.append(param)

                    param.set(0)


def turn_things_back_on():
    global device_params_turned_off

    if device_params_turned_off is None:
        return

    for param in device_params_turned_off:
        param.set(1)

    device_params_turned_off = None


def turn_lights_off_and_on():
    global device_params_turned_off

    if device_params_turned_off is None:
        turn_off_everything()
    else:
        turn_things_back_on()


button_1_released = True


def philips_action_handler():
    global philips_rotary_target, button_1_released

    t = devices.philips_switch.action.enum_type
    action = devices.philips_switch.action.get_enum_value()

    if action == t.button_1_press:
        philips_rotary_target = living_room
    if action == t.button_2_press:
        philips_rotary_target = kitchen
    if action == t.button_1_hold and button_1_released:
        button_1_released = False
        turn_lights_off_and_on()
    if action == t.button_1_hold_release:
        button_1_released = True


devices.philips_switch.action.add_listener(philips_action_handler)


def http_message_handler(payload):
    if "action" in payload:
        action = payload["action"]

        if action == "turn_off_all_lights":
            turn_lights_off_and_on()


# ==============================================================================
from flask import Flask, request
from emkyoot.message_loop import message_loop

app = Flask(__name__)


@app.route("/emkyoot")
def http_emkyoot_help():
    return (
        """Send commands to <code>/emkyoot/post</code>.</br>
</br>
Possible commands are:</br>
* <code>{"action": "turn_off_all_lights"}</code>
""",
        200,
    )


@app.route("/emkyoot/post", methods=["POST"])
def http_emkyoot_post():
    payload = request.get_json()

    def message_callback():
        http_message_handler(payload)

    message_loop.post_message(message_callback)

    return "", 200


# ==============================================================================
# This is meant for debugging purposes. You can also run this automation by issuing
# `emkyoot quicklaunch automation.py` in the terminal.
if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)

    # This is an alternative way to run the devices_client intended to help with debugging
    from emkyoot import quicklaunch, EmkyootConfig

    config = EmkyootConfig.load("config.toml")

    if config is not None:
        quicklaunch(devices, config)
