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

"""
Provides the functionality for the ``pyziggy run`` and ``pyziggy check`` subcommands.
"""

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
from .workarounds import applied_workarounds

logger = logging.getLogger(__name__)


class PyziggyConfig:
    """
    Used for parsing and checking the ``config.toml`` file, to be passed to
    :func:`run_command`.
    """

    def __init__(
        self,
        host: str,
        port: int,
        keepalive: int,
        base_topic: str,
        username: str | None,
        password: str | None,
        use_tls: bool,
        flask_port: int,
    ):
        self.host = host
        self.port = port
        self.keepalive = keepalive
        self.base_topic = base_topic
        self.flask_port = flask_port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    def write(self, config_file: Path) -> None:
        """
        Writes the configuration information to the specified file. Currently, this
        function isn't used by ``pyziggy``.
        """

        with open(config_file, "w") as f:
            toml.dump(
                {
                    "mqtt_server": {
                        "host": self.host,
                        "port": self.port,
                        "keepalive": self.keepalive,
                        "base_topic": self.base_topic,
                        "username": self.username,
                        "password": self.password,
                        "use_tls": self.use_tls,
                    },
                    "flask": {
                        "flask_port": self.flask_port,
                    },
                },
                f,
            )

    @staticmethod
    def load(config_file: Path | str) -> PyziggyConfig | None:
        """
        Loads the specified configuration file, checks its correctness and returns a
        :class:`PyziggyConfig` object if it passes all checks. Returns None otherwise.

        This function is used by ``pyziggy run`` to load and parse the ``config.toml``
        file in the current automation project directory.
        """

        try:
            config = toml.load(config_file)

            flask_port = 5001

            if "flask" in config.keys() and "flask_port" in config["flask"].keys():
                flask_port = config["flask"]["flask_port"]

            return PyziggyConfig(
                config["mqtt_server"]["host"],
                config["mqtt_server"]["port"],
                config["mqtt_server"]["keepalive"],
                config["mqtt_server"]["base_topic"],
                (
                    config["mqtt_server"]["username"]
                    if "username" in config["mqtt_server"]
                    else None
                ),
                (
                    config["mqtt_server"]["password"]
                    if "password" in config["mqtt_server"]
                    else None
                ),
                config["mqtt_server"]["use_tls"],
                flask_port,
            )

        except:
            return None

    @staticmethod
    def create_default() -> PyziggyConfig:
        """
        Creates a default configuration object.
        """

        return PyziggyConfig(
            "192.168.1.56", 1883, 60, "zigbee2mqtt", None, None, False, 5001
        )

    @staticmethod
    def write_default(config_file: Path) -> None:
        """
        Writes a default ``.toml`` file to the specified Path. This is used by the
        ``pyziggy run`` command to create the default ``config.toml`` file if one isn't
        present in the specified automation directory.
        """

        default_config = """[mqtt_server]
host = "192.168.1.56"
port = 1883
keepalive = 60
base_topic = "zigbee2mqtt"
use_tls = false

# If your MQTT server requires a username and password, you can provide them by
# uncommenting and setting the below values. In this case you probably need to
# enable the use_tls setting as well.
#
# username = "your_username"
# password = "your_password"

[flask]
flask_port = 5001
"""
        with open(config_file, "w") as f:
            f.write(default_config)


def _regenerate_device_definitions(available_devices_path: Path, config: PyziggyConfig):
    from .generator import DevicesGenerator

    generator = DevicesGenerator(available_devices_path)
    generator._connect(
        config.host,
        config.port,
        config.keepalive,
        config.base_topic,
        config.use_tls,
        config.username,
        config.password,
    )

    # The generator quits on its own when its job is finished
    generator._loop_forever()


def _regenerate_available_devices(project_root: Path, config: PyziggyConfig):
    autogenerate_dir = project_root / "pyziggy_autogenerate"

    if autogenerate_dir.exists():
        if not autogenerate_dir.is_dir():
            logger.fatal(
                f"pyziggy autogenerate directory exists and is not a directory: {autogenerate_dir}"
            )
            exit(1)
    else:
        autogenerate_dir.mkdir(parents=True, exist_ok=True)

    available_devices_path = autogenerate_dir / "available_devices.py"

    print(f"Regenerating device definitions in {available_devices_path.absolute()}...")
    _regenerate_device_definitions(available_devices_path, config)


def _run_mypy(
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
        [
            sys.executable,
            "-m",
            "mypy",
            "--check-untyped-defs",
            "--strict-equality",
            str(python_script_path),
        ],
        env=env,
    )

    return result.returncode == 0


class _ThreadedFlaskRunner:
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


def _install_sigint_handler():
    def signal_handler(sig, frame):
        print("\nSIGINT received. Shutting down...")
        message_loop.stop()

    signal.signal(signal.SIGINT, signal_handler)


T = TypeVar("T")


def _get_instance_of_type(module, type: Type[T]) -> Optional[T]:
    for name in dir(module):
        obj = getattr(module, name)

        if isinstance(obj, type):
            return obj

    return None


def _load_flask_object(devices_client_module_path: Path) -> Optional[Flask]:
    sys.path.append(str(devices_client_module_path.parent))

    devices_client_module = importlib.import_module(
        devices_client_module_path.name.replace(".py", "")
    )

    return _get_instance_of_type(devices_client_module, Flask)


def _load_devices_client(devices_client_module_path: Path) -> DevicesClient:
    sys.path.append(str(devices_client_module_path.parent))

    devices_client_module = importlib.import_module(
        devices_client_module_path.name.replace(".py", "")
    )

    devices_client = _get_instance_of_type(devices_client_module, DevicesClient)

    if devices_client is None:
        print(f"Couldn't find DevicesClient instance in {devices_client_module_path}")
        exit(1)

    return devices_client


def _get_devices_client_module_path(
    devices_client_param: DevicesClient | Path,
) -> Optional[Path]:
    if isinstance(devices_client_param, Path):
        return devices_client_param

    if len(sys.argv) > 0:
        argv0 = Path(sys.argv[0])

        if argv0.exists() and argv0.suffix == ".py":
            return argv0

    return None


def _pre_run_check(
    devices_client_param: DevicesClient | Path, config: PyziggyConfig, no_mypy: bool
):
    devices_client_module_path = _get_devices_client_module_path(devices_client_param)

    if devices_client_module_path is not None:
        _regenerate_available_devices(devices_client_module_path.parent, config)

        if not no_mypy:
            if _run_mypy(devices_client_module_path) == False:
                return False

    return True


def run_command(
    devices_client_param: DevicesClient | Path,
    config: PyziggyConfig,
    no_startup_query: bool = False,
    no_mypy: bool = False,
    flask_app: Flask | None = None,
    pre_run_check_only: bool = False,
) -> None:
    """
    This is the function that's called by the ``pyziggy run`` command-line program after
    the ``AvailableDevices`` type has been regenerated.

    :param devices_client_param: Either the DevicesClient object i.e. AvailableDevices, or the
                                 path to the module file that contains this object e.g.
                                 ``automation.py``. If it's the former, there is no need for
                                 importing, and :func:`run` can be called from the containing
                                 module file as well.
    :param config: A configuration object encapsulating all validated arguments to the
                   run subcommand. See :class:`PyziggyConfig`
    :param no_startup_query: If set to True, the command won't query Z2M for parameter
                             values on startup.
    :param no_mypy: If set to True, the command won't run mypy prior to entering
                    operation.
    :param flask_app: A ``flask.Flask`` object to serve HTTP requests.
    :param pre_run_check_only: Turns this function into the equivalent of the ``check``
                               subcommand.
    """

    check_success = _pre_run_check(devices_client_param, config, no_mypy)

    if not check_success:
        exit(1)

    if pre_run_check_only:
        if check_success:
            exit(0)
        exit(1)

    devices_client = (
        devices_client_param
        if isinstance(devices_client_param, DevicesClient)
        else _load_devices_client(devices_client_param)
    )

    if isinstance(devices_client_param, Path):
        flask_app = _load_flask_object(devices_client_param)

    _install_sigint_handler()

    flask_runner = (
        _ThreadedFlaskRunner(flask_app, config.flask_port)
        if flask_app is not None
        else None
    )

    applied_workarounds._apply(devices_client)

    if no_startup_query:
        print(
            "Using --skip_initial_query. Initial parameter values will not reflect the devices' true states."
        )
        devices_client._set_skip_initial_query(True)

    devices_client._connect(
        config.host, config.port, config.keepalive, config.base_topic
    )

    print("Starting message loop. Send SIGINT (CTRL+C) to quit.")

    devices_client._loop_forever()

    if flask_runner is not None:
        flask_runner.stop()
