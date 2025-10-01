# Random notes

These are random notes for myself and probably not a good substitute for the official documentation of e.g. Zigbee2MQTT.

## Zigbee2MQTT

### Installing

I made the following script in an effort to install Zigbee2MQTT in a way where it's easy to delete all installation files and dependencies later. There's no way around having to use `pnpm`, so I did have to add an **Uninstalling** section after all.

```
PROJECT_DIRECTORY="$HOME/Developer/zigbee2mqtt"
mkdir -p "$PROJECT_DIRECTORY"
pushd "$PROJECT_DIRECTORY"
touch requirements.txt
~/Developer/Python/pyziggy/util/pyziggy-setup --use-cwd setup
source .venv/bin/activate
pip install nodeenv
nodeenv -p

# The -p switch instructed nodeenv add node.js related stuff to the virtual
# environment. We reactivate the venv to ensure that nodeenv added paths are
# also active.
deactivate
source .venv/bin/activate

# --save-dev means we only need this for running/development, and avoids
# adding pnpm to the dependencies of zigbee2mqtt.
npm install pnpm --save-dev

export PATH="$PROJECT_DIRECTORY/node_modules/.bin:$PATH"
git clone --depth 1 --branch 2.6.1 https://github.com/Koenkk/zigbee2mqtt.git
pushd zigbee2mqtt
pnpm install --frozen-lockfile
popd
popd
```

To launch Zigbee2MQTT:

```
pnpm start
```

After the onboarding, the configuration will be saved in `"$PROJECT_DIRECTORY/zigbee2mqtt/data/configuration.yaml"`.

### Uninstalling

Delete the installation directory, plus the path returned by

```
pnpm store path
```

, which should point somewhere to `~/Library/pnpm`. `pnpm` downloads stuff to a global store (unlike `npm`), that is not removed when you delete the project directory.


## Execution model and the pyziggy runner

Pyziggy has an event driven architecture where it maintains communication with MQTT and optionally with a Flask webserver. Because of this it needs to have an infinite message loop. When you issue the command `pyziggy run automation.py` it launches the *pyziggy runner* that manages this message loop. 

Because of this pyziggy automations aren't executed directly as Python scripts. A pyziggy automation is actually a Python module. The examples refer to it as `automation.py`, but naturally you can call it anything else.

To create a pyziggy automation, you need to write a Python module i.e. a `.py` file, and inside this module you need to create exactly one object of the type `pyziggy_autogenerate.available_devices.AvailableDevices`. Then you need to issue the `pyziggy run automation.py` command in the terminal. This command launches the pyziggy runner, and it will import your automation module and use reflection to find the one `AvailableDevices` object in it. The runner will trigger events on the `AvailableDevices` object based on the MQTT messages it receives. Your automation module code can subscribe to these events. The first event that fires during a successful run is `AvailableDevices.on_connect`, so you could use this as an entry point.

The pyziggy runner runs indefinitely until either the SIGINT signal is received, or the `pyziggy.message_loop.message_loop` is stopped. Your automation code can call `stop()` or `stop_after_one_second()` on `pyziggy.message_loop.message_loop` if it wants to make the runner exit.
