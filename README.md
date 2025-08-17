# easterobot

[![CI : Docs](https://github.com/Dashstrom/easterobot/actions/workflows/docs.yml/badge.svg)](https://github.com/Dashstrom/easterobot/actions/workflows/docs.yml) [![CI : Lint](https://github.com/Dashstrom/easterobot/actions/workflows/lint.yml/badge.svg)](https://github.com/Dashstrom/easterobot/actions/workflows/lint.yml) [![CI : Tests](https://github.com/Dashstrom/easterobot/actions/workflows/tests.yml/badge.svg)](https://github.com/Dashstrom/easterobot/actions/workflows/tests.yml) [![PyPI : easterobot](https://img.shields.io/pypi/v/easterobot.svg)](https://pypi.org/project/easterobot) [![Python : versions](https://img.shields.io/pypi/pyversions/easterobot.svg)](https://pypi.org/project/easterobot) [![License : MIT](https://img.shields.io/badge/license-MIT-green.svg)](https://github.com/Dashstrom/easterobot/blob/main/LICENSE)

Discord bot for easter.

## Documentation

Documentation is available on <https://dashstrom.github.io/easterobot>.

## Installation

```bash
# Using pip
pip install easterobot
# Using uv (install in your project dependencies)
uv add easterobot
# Using pipx (install as a tool in a venv)
pipx install easterobot
# Using uv (install as a tool in a venv)
uv tool install easterobot
```

## Usage as CLI

Once installed, you can use it directly.

```bash
easterobot run -t YOU_MUST_PUT_YOUR_TOKEN_HERE
```

Or you can generate a custom configuration for your own needs !

```bash
easterobot generate -i data
easterobot run -c data/config.yml
```

## Usage with Docker

You can install `easterobot` using [uv](https://docs.astral.sh/uv/getting-started/installation) from [PyPI](https://pypi.org/project).

```bash
git clone https://github.com/Dashstrom/easterobot
cd easterobot
echo "DISCORD_TOKEN=YOU_MUST_PUT_YOUR_TOKEN_HERE" > .env

# Can be unsafe (and for each update)
chmod -R 700 . && mkdir data -p && chmod 777 data

# Run the docker container
docker compose up -d

# Stop it
docker compose stop

# Remove the container (not the data)
docker compose down --rmi all

# Update
git reset --hard HEAD && git pull

# One-line update
docker compose down --rmi all && git reset --hard HEAD && git pull && chmod -R 700 . && mkdir data -p && chmod 777 data && docker compose up -d
```

## Configuration directory

```text
data                          Root directory
├── .gitignore                Avoid pushing sensitive data
├── config.yml                Configuration file
├── easterobot.db             Database
├── logs                      Logging directory
│   ├── easterobot.log        Latest log file
│   └── easterobot.log.1      Rotating log file
└── resources                 Resource directory
    ├── config.example.yml    An example of config
    ├── credits.txt           Credits of emotes
    ├── emotes                Directory loaded as application emotes
    │   ├── eggs              Directory for eggs
    │   |   └── egg_01.png    Emoji to use for egg
    │   ├── icons             Misc emotes to load
    │   │   └── arrow.png     Emoji used in messages
    │   ├── placements        Directory for emoji used in grid
    │   │   └── s1.png        Single blue emoji with one on it
    │   └── skyjo             Skyjo cards
    │       └── skyjo_m1.png  Card with minus -1 with deep blue
    ├── logging.conf          Logging configuration
    ├── alembic.ini           Configure for alembic
    └── logo.png              Logo used by the bot
```

## Development

### Contributing

Contributions are very welcome. Tests can be run with `poe check`, please ensure the coverage at least stays the same before you submit a pull request.

### Prerequisite

First, You need to install [git](https://git-scm.com) following [the official guide](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and configure it.

Then, you need to install [uv](https://docs.astral.sh/uv/getting-started/installation) and update shell path with this command:

```bash
uv tool update-shell
```

Finally, run these commands for setup the project with dev dependencies.

```bash
git clone https://github.com/Dashstrom/easterobot
cd easterobot
uv sync --all-extras --python 3.10
uv run poe setup
```

### Poe

Poe is available for help you to run tasks: `uv run poe {task}` or `poe task` within the venv.

```text
test                  Run test suite.
lint                  Run linters: ruff checker and ruff formatter and mypy.
format                Run linters in fix mode.
check                 Run all checks: lint, test and docs.
check-tag             Check if the current tag match the version.
cov                   Run coverage for generate report and html.
open-cov              Open html coverage report in webbrowser.
doc                   Build documentation.
open-doc              Open documentation in webbrowser.
setup                 Setup pre-commit.
pre-commit            Run pre-commit.
clean                 Clean cache files.
```

### How to add dependency

```bash
uv add 'PACKAGE'
```

### Ignore illegitimate warnings

To ignore illegitimate warnings you can add :

- **# noqa: ERROR_CODE** on the same line for ruff.
- **# type: ignore[ERROR_CODE]** on the same line for mypy.
- **# pragma: no cover** on the same line to ignore line for coverage.
- **# doctest: +SKIP** on the same line for doctest.

### Install as service

```bash
E_NOTROOT=87 # Non-root exit error.
E_INSTALLED=1

if ! $(sudo -l &> /dev/null); then
  >&2 echo 'Error: root privileges are needed to run this script'
  exit $E_NOTROOT
fi

if ! id easterobot >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /home/easterobot easterobot
fi

if [ ! -d /home/easterobot/easterobot ]; then
  sudo -u easterobot -g easterobot -- git clone https://github.com/Dashstrom/easterobot /home/easterobot/easterobot
fi

cd /home/easterobot/easterobot
systemctl disable easterobot || true
systemctl stop easterobot || true
sudo -u easterobot -g easterobot -- git pull
sudo -u easterobot -g easterobot -- python3 -m venv /home/easterobot/easterobot/.venv
sudo -u easterobot -g easterobot -- /home/easterobot/easterobot/.venv/bin/python3 -m pip install .
sudo -u easterobot -g easterobot -- /home/easterobot/easterobot/.venv/bin/easterobot generate -i /home/easterobot/easterobot/data
if [ ! -f /lib/systemd/system/easterobot.service ]; then
  mkdir -p /lib/systemd/system
  cat > /lib/systemd/system/easterobot.service << EOF
[Unit]
Description=Easterobot
After=network-online.target

[Service]
Type=exec
ExecStart=/home/easterobot/easterobot/.venv/bin/easterobot run -c /home/easterobot/easterobot/data/config.yml
WorkingDirectory=/home/easterobot/easterobot
StandardOutput=inherit
StandardError=inherit
Restart=always
User=easterobot

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
fi
systemctl enable easterobot
systemctl start easterobot
systemctl status easterobot
```

## License

This work is licensed under [MIT](https://github.com/Dashstrom/easterobot/blob/main/LICENSE).
