"""Module for command line interface."""

import argparse
import logging
import sys
import warnings
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn, Optional, TextIO, Union

from alembic.config import CommandLine

from easterobot.bot import Easterobot
from easterobot.config import DEFAULT_CONFIG_PATH, load_config_from_path
from easterobot.info import __issues__, __project__, __summary__, __version__

LOG_LEVELS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]
logger = logging.getLogger(__name__)
cmd_alembic = CommandLine(prog="easterobot alembic")


def showwarning(  # pragma: no cover
    message: Union[Warning, str],
    category: type[Warning],
    filename: str,
    lineno: int,
    file: Optional[TextIO] = None,  # noqa: ARG001
    line: Optional[str] = None,  # noqa: ARG001
) -> None:
    """Show warning within the logger."""
    for module_name, module in sys.modules.items():  # noqa: B007
        module_path = getattr(module, "__file__", None)
        if module_path and Path(module_path).samefile(filename):
            break
    else:
        module_name = Path(filename).stem
    msg = f"{category.__name__}: {message}"
    logger = logging.getLogger(module_name)
    try:
        _, _, func, info = logger.findCaller()
    except ValueError:  # pragma: no cover
        func, info = "(unknown function)", None
    record = logger.makeRecord(
        logger.name,
        logging.WARNING,
        filename,
        lineno,
        msg,
        (),
        None,
        func,
        None,
        info,
    )
    logger.handle(record)


class HelpArgumentParser(argparse.ArgumentParser):
    """Parser for show usage on error."""

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
        help="verbose mode, enable INFO and DEBUG messages.",
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


def setup_logging(*, verbose: Optional[bool] = None) -> None:
    """Do setup logging."""
    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
    )
    warnings.showwarning = showwarning


def entrypoint(argv: Optional[Sequence[str]] = None) -> None:
    """Entrypoint for command line interface."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        parser = get_parser()
        namespace = parser.parse_args(args)
        if namespace.action == "run":
            setup_logging(verbose=namespace.verbose)
            bot = Easterobot.from_config(
                namespace.config,
                token=namespace.token,
                env=namespace.env,
            )
            bot.auto_run()
        elif namespace.action == "generate":
            setup_logging(verbose=namespace.verbose)
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
    except Exception as err:  # NoQA: BLE001  # pragma: no cover
        setup_logging(verbose=True)
        logger.critical(
            "Unexpected error (%s, version %s)",
            __project__,
            __version__,
            exc_info=err,
        )
        logger.critical("Please, report this error to %s.", __issues__)
        sys.exit(1)
