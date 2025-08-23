(cookbook)=
# Cookbook

## Automation building blocks

The following are simple examples for typical use-cases. They assume an automation project set up in the way laid out in the <a href="index.html#a-minimal-automation-project">minimal automation project</a> section.

### Chech

Problems, there are.

## Working with the `pyziggy-setup` script

```{warning}
**The script makes changes to the directory it's in. Not the current working directory.** And I might change this behavior in future versions, so use this script at your own peril.
```

### Set up a project directory with a `.venv` directory and pyziggy installed

We'll create a new project in the `my_automation` directory. This requires that `pyenv` is installed on your system.

```
mkdir my_automation
cd my_automation
```

The next block downloads the `pyziggy-setup` script into `my_automation`, downloads an appropriate version using `pyenv`, creates a `.venv` subdirectory, and installs `pyziggy` in it.

```
curl -fsSL https://raw.githubusercontent.com/bebump/pyziggy/refs/heads/main/util/pyziggy-setup -o pyziggy-setup
chmod u+x pyziggy-setup
./pyziggy-setup setup
```

You can now activate the virtual environment, and create your pyziggy project

```
source .venv/bin/activate
pyziggy run automation.py
```
