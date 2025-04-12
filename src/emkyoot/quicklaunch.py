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

from __future__ import annotations

import importlib
import logging
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional, TypeVar, Type

import toml
from flask import Flask

from .devices_client import DevicesClient
from .message_loop import message_loop

logger = logging.getLogger(__name__)


class EmkyootConfig:
    def __init__(
        self,
        host: str,
        port: int,
        keepalive: int,
        base_topic: str,
        flask_port: int,
    ):
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.base_topic = base_topic
        self.flask_port = flask_port

    def write(self, config_file: Path):
        with open(config_file, "w") as f:
            toml.dump(
                {
                    "mqtt_server": {
                        "host": self.host,
                        "port": self.port,
                        "keepalive": self.keepalive,
                        "base_topic": self.base_topic,
                    },
                    "flask": {
                        "flask_port": self.flask_port,
                    },
                },
                f,
            )

    @staticmethod
    def load(config_file: Path | str) -> EmkyootConfig | None:
        try:
            config = toml.load(config_file)

            flask_port = 5001

            if "flask" in config.keys() and "flask_port" in config["flask"].keys():
                flask_port = config["flask"]["flask_port"]

            return EmkyootConfig(
                config["mqtt_server"]["host"],
                config["mqtt_server"]["port"],
                config["mqtt_server"]["keepalive"],
                config["mqtt_server"]["base_topic"],
                flask_port,
            )

        except:
            return None

    @staticmethod
    def create_default() -> EmkyootConfig:
        return EmkyootConfig("192.168.1.56", 1883, 60, "zigbee2mqtt", 5001)


def regenerate_device_definitions(available_devices_path: Path, config: EmkyootConfig):
    from .devices_client_generator import DevicesGenerator

    generator = DevicesGenerator(available_devices_path)
    generator.connect(config.host, config.port, config.keepalive, config.base_topic)

    # The generator quits on its own when its job is finished
    generator.loop_forever()


def regenerate_available_devices(project_root: Path, config: EmkyootConfig):
    autogenerate_dir = project_root / "emkyoot_autogenerate"

    if autogenerate_dir.exists():
        if not autogenerate_dir.is_dir():
            logger.fatal(
                f"emkyoot autogenerate directory exists and is not a directory: {autogenerate_dir}"
            )
            exit(1)
    else:
        autogenerate_dir.mkdir(parents=True, exist_ok=True)

    available_devices_path = autogenerate_dir / "available_devices.py"

    print(f"Regenerating device definitions in {available_devices_path.absolute()}...")
    regenerate_device_definitions(available_devices_path, config)


def run_mypy(
    python_script_path: Path,
) -> bool:
    env = os.environ.copy()

    # mypy bug: Errors aren't shown in imports when the PYTHONPATH is set. This isn't just true
    # for excluded folders, but in general.
    # https://github.com/python/mypy/issues/16973
    if "PYTHONPATH" in env:
        del env["PYTHONPATH"]

    print(f"Running mypy on {python_script_path}...")

    result = subprocess.run(
        ["mypy", "--check-untyped-defs", "--strict-equality", str(python_script_path)],
        env=env,
    )

    return result.returncode == 0


class ThreadedFlaskRunner:
    def __init__(self, flask_app: Flask, port: int):
        from werkzeug.serving import make_server

        self.flask_server = make_server("0.0.0.0", port, flask_app)
        self.thread = threading.Thread(target=self.flask_server.serve_forever)

        print(f"Launching flask server on port {port}")

        self.thread.start()

    def stop(self):
        if self.thread is not None:
            self.flask_server.shutdown()
            self.thread.join(2)


def install_sigint_handler():
    def signal_handler(sig, frame):
        print("\nSIGINT received. Shutting down...")
        message_loop.stop()

    signal.signal(signal.SIGINT, signal_handler)


T = TypeVar("T")


def get_instance_of_type(module, type: Type[T]) -> Optional[T]:
    for name in dir(module):
        obj = getattr(module, name)

        if isinstance(obj, type):
            return obj

    return None


def load_flask_object(devices_client_module_path: Path) -> Optional[Flask]:
    sys.path.append(str(devices_client_module_path.parent))

    devices_client_module = importlib.import_module(
        devices_client_module_path.name.replace(".py", "")
    )

    return get_instance_of_type(devices_client_module, Flask)


def load_devices_client(devices_client_module_path: Path) -> DevicesClient:
    sys.path.append(str(devices_client_module_path.parent))

    devices_client_module = importlib.import_module(
        devices_client_module_path.name.replace(".py", "")
    )

    devices_client = get_instance_of_type(devices_client_module, DevicesClient)

    if devices_client is None:
        print(f"Couldn't find DevicesClient instance in {devices_client_module_path}")
        exit(1)

    return devices_client


def get_devices_client_module_path(
    devices_client_param: DevicesClient | Path,
) -> Optional[Path]:
    if isinstance(devices_client_param, Path):
        return devices_client_param

    if len(sys.argv) > 0:
        argv0 = Path(sys.argv[0])

        if argv0.exists() and argv0.suffix == ".py":
            return argv0

    return None


def quicklaunch(
    devices_client_param: DevicesClient | Path,
    config: EmkyootConfig,
    flask_app: Flask | None = None,
):
    devices_client_module_path = get_devices_client_module_path(devices_client_param)

    if devices_client_module_path is not None:
        regenerate_available_devices(devices_client_module_path.parent, config)
        if run_mypy(devices_client_module_path) == False:
            exit(1)

    devices_client = (
        devices_client_param
        if isinstance(devices_client_param, DevicesClient)
        else load_devices_client(devices_client_param)
    )

    if isinstance(devices_client_param, Path):
        flask_app = load_flask_object(devices_client_param)

    install_sigint_handler()

    flask_runner = (
        ThreadedFlaskRunner(flask_app, config.flask_port)
        if flask_app is not None
        else None
    )

    devices_client.connect(
        config.host, config.port, config.keepalive, config.base_topic
    )

    print("Starting message loop. Send SIGINT (CTRL+C) to quit.")

    devices_client.loop_forever()

    if flask_runner is not None:
        flask_runner.stop()
