.. role:: bash(code)
  :language: bash

**********
easterobot
**********

|ci-docs| |ci-lint| |ci-tests| |pypi| |versions| |license|

.. |ci-docs| image:: https://github.com/Dashstrom/easterobot/actions/workflows/docs.yml/badge.svg
  :target: https://github.com/Dashstrom/easterobot/actions/workflows/docs.yml
  :alt: CI : Docs

.. |ci-lint| image:: https://github.com/Dashstrom/easterobot/actions/workflows/lint.yml/badge.svg
  :target: https://github.com/Dashstrom/easterobot/actions/workflows/lint.yml
  :alt: CI : Lint

.. |ci-tests| image:: https://github.com/Dashstrom/easterobot/actions/workflows/tests.yml/badge.svg
  :target: https://github.com/Dashstrom/easterobot/actions/workflows/tests.yml
  :alt: CI : Tests

.. |pypi| image:: https://img.shields.io/pypi/v/easterobot.svg
  :target: https://pypi.org/project/easterobot
  :alt: PyPI : easterobot

.. |versions| image:: https://img.shields.io/pypi/pyversions/easterobot.svg
  :target: https://pypi.org/project/easterobot
  :alt: Python : versions

.. |license| image:: https://img.shields.io/badge/license-MIT-green.svg
  :target: https://github.com/Dashstrom/easterobot/blob/main/LICENSE
  :alt: License : MIT

Description
###########

Discord bot for Easter.

Documentation
#############

Documentation is available on https://dashstrom.github.io/easterobot

Prerequisite
############

For using easterobot you will need a token, you can follow `the discord.py Guide for get one <https://discordpy.readthedocs.io/en/stable/discord.html>`_.

Usage as CLI
############

You can install :bash:`easterobot` using `uv <https://docs.astral.sh/uv/getting-started/installation>`_
from `PyPI <https://pypi.org/project>`_.

..  code-block:: bash

  pip install uv
  uv tool install easterobot
  # or uv tool install git+https://github.com/Dashstrom/easterobot

Once installed, you can use it directly.

..  code-block:: bash

  easterobot run -t YOU_MUST_PUT_YOUR_TOKEN_HERE

Or you can generate a custom configuration for your own needs !

..  code-block:: bash

  easterobot generate -i data
  easterobot run -c data/config.yml

Usage with Docker
#################

You can install :bash:`easterobot` using `uv <https://docs.astral.sh/uv/getting-started/installation>`_
from `PyPI <https://pypi.org/project>`_

..  code-block:: bash

    git clone https://github.com/Dashstrom/easterobot
    cd easterobot
    echo "DISCORD_TOKEN=YOU_MUST_PUT_YOUR_TOKEN_HERE" > .env

    # Can be unsafe
    chmod -R 700 .
    mkdir data
    chmod 777 data

    # Run the docker container
    docker compose up -d

    # Stop it
    docker compose stop

    # Remove the container (not the data)
    docker compose down --rmi all

Configuration directory
#######################

..  code-block:: text

  data                        Root directory
  ├── .gitignore              Avoid pushing sensitive data
  ├── config.yml              Configuration file
  ├── easterobot.db           Database
  ├── logs                    Logging directory
  │   ├── easterobot.log      Latest log file
  │   └── easterobot.log.1    Rotating log file
  └── resources               Resource directory
      ├── config.example.yml  An example of config
      ├── credits.txt         Credits of emotes
      ├── emotes              Directory loaded as application emotes
      │   ├── eggs            Directory for eggs
      │   |   └── egg_01.png  Emoji to use for egg
      │   └── icons           Misc emotes to load
      │       └── arrow.png   Emoji used in messages
      ├── logging.conf        Logging configuration
      ├── alembic.ini         Configure for alembic
      └── logo.png            Logo used by the bot

Development
###########

Contributing
************

Contributions are very welcome. Tests can be run with :bash:`poe check`, please
ensure the coverage at least stays the same before you submit a pull request.

Setup
*****

You need to install `uv <https://docs.astral.sh/uv/getting-started/installation>`_
and `Git <https://git-scm.com/book/en/v2/Getting-Started-Installing-Git>`_
for work with this project.

..  code-block:: bash

  git clone https://github.com/Dashstrom/easterobot
  cd easterobot
  uv sync
  uv run poe setup

Poe
********

Poe is available for help you to run tasks.

..  code-block:: text

  test           Run test suite.
  lint           Run linters: ruff checker and ruff formatter and mypy.
  format         Run linters in fix mode.
  check          Run all checks: lint, test and docs.
  check-tag      Check if the current tag match the version.
  cov            Run coverage for generate report and html.
  open-cov       Open html coverage report in webbrowser.
  docs           Build documentation.
  open-docs      Open documentation in webbrowser.
  setup          Setup pre-commit.
  pre-commit     Run pre-commit.
  commit         Test, commit and push.
  clean          Clean cache files.

Skip commit verification
************************

If the linting is not successful, you can't commit.
For forcing the commit you can use the next command :

..  code-block:: bash

  git commit --no-verify -m 'MESSAGE'

Commit with commitizen
**********************

To respect commit conventions, this repository uses
`Commitizen <https://github.com/commitizen-tools/commitizen?tab=readme-ov-file>`_.

..  code-block:: bash

  cz c

How to add dependency
*********************

..  code-block:: bash

  uv add 'PACKAGE'

Ignore illegitimate warnings
****************************

To ignore illegitimate warnings you can add :

- **# noqa: ERROR_CODE** on the same line for ruff.
- **# type: ignore[ERROR_CODE]** on the same line for mypy.
- **# pragma: no cover** on the same line to ignore line for coverage.
- **# doctest: +SKIP** on the same line for doctest.

Uninstall
#########

..  code-block:: bash

  pipx uninstall easterobot

License
#######

This work is licensed under `MIT <https://github.com/Dashstrom/easterobot/blob/main/LICENSE>`_.
