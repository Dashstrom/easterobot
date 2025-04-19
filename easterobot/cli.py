"""Module for command line interface."""

import argparse
import logging
import sys
from collections.abc import Sequence
from traceback import print_exc
from typing import NoReturn, Optional

from alembic.config import CommandLine

from easterobot.config import load_config_from_path

from .bot import Easterobot
from .config import DEFAULT_CONFIG_PATH
from .info import __issues__, __summary__, __version__

LOG_LEVELS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
logger = logging.getLogger(__name__)
cmd_alembic = CommandLine(prog="easterobot alembic")


class HelpArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:  # pragma: no cover
        """Handle error from argparse.ArgumentParser."""
        self.print_help(sys.stderr)
        self.exit(2, f"{self.prog}: error: {message}\n")


def get_parser() -> argparse.ArgumentParser:
    """Prepare ArgumentParser."""
    parser = HelpArgumentParser(
        prog="easterobot",
        description=__summary__,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s, version {__version__}",
    )

    # Add subparsers
    subparsers = parser.add_subparsers(
        help="desired action to perform",
        dest="action",
        required=True,
    )

    # Add parent parser with common arguments
    parent_parser = HelpArgumentParser(add_help=False)
    parent_parser.add_argument(
        "-v",
        "--verbose",
        help="verbose mode, enable DEBUG messages.",
        action="store_true",
        required=False,
    )
    parent_parser.add_argument(
        "-t",
        "--token",
        help="run using a token and the default configuration.",
    )
    parent_parser.add_argument(
        "-e",
        "--env",
        help="load token from DISCORD_TOKEN environnement variable.",
        action="store_true",
    )

    # Parser for run command
    run_parser = subparsers.add_parser(
        "run",
        parents=[parent_parser],
        help="start the bot.",
    )
    run_parser.add_argument(
        "-c",
        "--config",
        help=f"path to configuration, default to {DEFAULT_CONFIG_PATH}.",
        default=DEFAULT_CONFIG_PATH,
    )

    # Parser for generate command
    generate_parser = subparsers.add_parser(
        "generate",
        parents=[parent_parser],
        help="generate a configuration.",
    )
    generate_parser.add_argument(
        "-i",
        "--interactive",
        help="ask questions for create a ready to use config.",
        action="store_true",
    )
    generate_parser.add_argument("destination", default=".")

    # Parser for alembic
    alembic_parser = subparsers.add_parser(
        "alembic",
        parents=[cmd_alembic.parser],  # type: ignore[list-item]
        help="use alembic with bot context.",
        add_help=False,
    )
    for action in alembic_parser._actions:  # noqa: SLF001
        if "--config" in action.option_strings:
            alembic_parser._handle_conflict_resolve(  # noqa: SLF001
                None,  # type: ignore[arg-type]
                [("--config", action), ("-c", action)],
            )
            break
    alembic_parser.add_argument(
        "-c",
        "--config",
        help=f"path to configuration, default to {DEFAULT_CONFIG_PATH}.",
        default=DEFAULT_CONFIG_PATH,
    )
    return parser


def setup_logging(verbose: Optional[bool] = None) -> None:
    """Do setup logging."""
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    )


def entrypoint(argv: Optional[Sequence[str]] = None) -> None:
    """Entrypoint for command line interface."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        parser = get_parser()
        namespace = parser.parse_args(args)
        if namespace.action == "run":
            setup_logging(namespace.verbose)
            bot = Easterobot.from_config(
                namespace.config,
                token=namespace.token,
                env=namespace.env,
            )
            bot.auto_run()
        elif namespace.action == "generate":
            setup_logging(namespace.verbose)
            Easterobot.generate(
                destination=namespace.destination,
                token=namespace.token,
                env=namespace.env,
                interactive=namespace.interactive,
            )
        elif namespace.action == "alembic":
            if not hasattr(namespace, "cmd"):
                # see http://bugs.python.org/issue9253, argparse
                # behavior changed incompatibly in py3.3
                parser.error("too few arguments")
            else:
                config = load_config_from_path(namespace.config)
                cfg = config.alembic_config(namespace)
                cmd_alembic.run_cmd(cfg, namespace)
        else:
            parser.error("No command specified")  # pragma: no cover
    except BaseException as err:  # NoQA: BLE001  # pragma: no cover
        setup_logging(verbose=True)
        print_exc()
        logger.critical("Unexpected error", exc_info=err)
        logger.critical("Please, report this error to %s.", __issues__)
        sys.exit(1)
