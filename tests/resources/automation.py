import os
from pathlib import Path

from device_helpers import (
    IkeaN2CommandRepeater,
    PhilipsTapDialRotaryHelper,
)
from emkyoot.device_bases import LightWithColorTemp, LightWithColor
from emkyoot.parameters import (
    SettableBinaryParameter,
    SettableToggleParameter,
    SettableAndQueryableBinaryParameter,
    SettableAndQueryableToggleParameter,
)
from emkyoot.util import LightWithDimmingScalable as L2S
from emkyoot.util import ScaleMapper
from emkyoot_autogenerate.available_devices import AvailableDevices


# Interprets the provided path constituents relative to the location of this
# script, and returns an absolute Path to the resulting location.
#
# E.g. rel_to_py(".") returns an absolute path to the directory containing this
# script.
def rel_to_py(*paths) -> Path:
    return Path(
        os.path.realpath(
            os.path.join(os.path.realpath(os.path.dirname(__file__)), *paths)
        )
    )


devices = AvailableDevices()


kitchen = ScaleMapper(
    [
        (L2S(devices.hue_lightstrip), 0.0, 0.54),
        (L2S(devices.dining_light_1), 0.56, 0.93),
        (L2S(devices.dining_light_2), 0.56, 0.93),
        (L2S(devices.kitchen_light), 0.95, 1.0),
    ],
    [0.55, 0.94],
    lambda: print("\a"),
)

living_room = ScaleMapper(
    [
        (L2S(devices.standing_lamp), 0.0, 0.7),
        (L2S(devices.couch), 0.2, 0.7),
        (L2S(devices.reading_lamp), 0.7, 1.0),
    ]
)


def set_mired(mired):
    for device in devices.get_devices():
        if isinstance(device, LightWithColorTemp):
            device.color_temp.set(mired)


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
    elif action == types.arrow_left_click:
        set_mired(417)
    elif action == types.arrow_right_click:
        set_mired(370)


ikea_remote_action_broadcaster = IkeaN2CommandRepeater(devices.ikea_remote)
ikea_remote_action_broadcaster.repeating_action.add_listener(ikea_remote_action_handler)


def kitchen_dimmer(step: int):
    kitchen.add(step / 8 * 0.022)


def living_room_dimmer(step: int):
    living_room.add(step / 8 * 0.022)


def hue_changer(step: int):
    for device in devices.get_devices():
        if isinstance(device, LightWithColor):
            device.color_hs.hue.set((device.color_hs.hue.get() + step) % 360)


def saturation_changer(step: int):
    for device in devices.get_devices():
        if isinstance(device, LightWithColor):
            device.color_hs.saturation.add(step)


philips_dial_handler = living_room_dimmer

rotary_helper = PhilipsTapDialRotaryHelper(devices.philips_switch)
rotary_helper.on_rotate.add_listener(lambda step: philips_dial_handler(step))

device_params_turned_off: list | None = None


def turn_off_everything():
    global device_params_turned_off

    device_params_turned_off = []

    for device in devices.get_devices():
        if device == devices.toilet:
            continue

        for name, param in vars(device).items():
            if name == "state":
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


button_1_released = True
button_2_released = True


def philips_button_handler():
    global philips_dial_handler, button_1_released, button_2_released

    t = devices.philips_switch.action.enum_type
    action = devices.philips_switch.action.get_enum_value()

    if action == t.button_1_press:
        philips_dial_handler = living_room_dimmer
    if action == t.button_2_press:
        philips_dial_handler = kitchen_dimmer
    if action == t.button_3_press:
        philips_dial_handler = hue_changer
    if action == t.button_4_press:
        philips_dial_handler = saturation_changer
    if action == t.button_1_hold and button_1_released:
        button_1_released = False
        turn_off_everything()
    if action == t.button_2_hold and button_2_released:
        button_2_released = False
        turn_things_back_on()
    if action == t.button_1_hold_release:
        button_1_released = True
    if action == t.button_2_hold_release:
        button_2_released = True


devices.philips_switch.action.add_listener(philips_button_handler)
