"""Module for command line interface."""

import argparse
import logging
import sys
from collections.abc import Sequence
from typing import NoReturn, Optional

from .bot import DEFAULT_CONFIG_PATH, Easterobot
from .info import __issues__, __summary__, __version__

LOG_LEVELS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
logger = logging.getLogger(__name__)


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

    # Parser of hello command
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

    # Parser of hello command
    run_parser = subparsers.add_parser(
        "generate",
        parents=[parent_parser],
        help="generate a configuration.",
    )
    run_parser.add_argument(
        "-i",
        "--interactive",
        help="ask questions for create a ready to use config.",
        action="store_true",
    )
    run_parser.add_argument("destination", default=".")
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
    try:
        parser = get_parser()
        args = parser.parse_args(argv)
        setup_logging(args.verbose)
        if args.action == "run":
            bot = Easterobot.from_config(
                args.config,
                token=args.token,
                env=args.env,
            )
            bot.auto_run()
        elif args.action == "generate":
            Easterobot.generate(
                destination=args.destination,
                token=args.token,
                env=args.env,
                interactive=args.interactive,
            )
        else:
            parser.error("No command specified")  # pragma: no cover
    except Exception as err:  # NoQA: BLE001  # pragma: no cover
        logger.critical("Unexpected error", exc_info=err)
        logger.critical("Please, report this error to %s.", __issues__)
        sys.exit(1)
