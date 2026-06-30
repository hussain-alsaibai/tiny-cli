"""tiny-cli: Zero-dependency CLI builder for Python.

Compose command-line interfaces with decorators, type coercion, color output,
and prompts. argparse replacement for the 90% case.

Single file, no deps, MIT, fully typed.

Example:
    @app.command()
    def greet(name: str, times: int = 1, shout: bool = False):
        '''Say hello.'''
        msg = f"Hello, {name}!" * times
        if shout:
            msg = msg.upper()
        print(msg)

    app.run()
"""

from __future__ import annotations

import argparse
import inspect
import os
import shlex
import sys
import textwrap
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    get_type_hints,
)

__version__ = "0.1.0"
__all__ = ["App", "command", "option", "argument", "confirm", "prompt", "echo", "style"]


# ---------------------------------------------------------------------------
# ANSI color helpers (auto-disabled if not a TTY or NO_COLOR set)
# ---------------------------------------------------------------------------

_NO_COLOR = "NO_COLOR" in os.environ or (
    not sys.stdout.isatty() and "TINY_CLI_FORCE_COLOR" not in os.environ
)


def _wrap(code: str) -> Callable[..., str]:
    def inner(text: str, **kw: Any) -> str:
        if kw.get("color", True) is False or _NO_COLOR:
            return str(text)
        return f"\033[{code}m{text}\033[0m"
    return inner


# Build a `style` namespace with all the colors.
class _Style:
    """Namespace for ANSI color helpers."""

    def __init__(self) -> None:
        self.red = _wrap("31")
        self.green = _wrap("32")
        self.yellow = _wrap("33")
        self.blue = _wrap("34")
        self.magenta = _wrap("35")
        self.cyan = _wrap("36")
        self.bold = _wrap("1")
        self.dim = _wrap("2")
        self.underline = _wrap("4")
        self.invert = _wrap("7")
        self.white = _wrap("37")
        self.gray = _wrap("90")

    def __call__(self, text: str, **kw: Any) -> str:
        return self.cyan(text, **kw)  # default: cyan

    def __getattr__(self, name: str) -> Callable[..., str]:
        # fall back: any unknown color → bold
        return _wrap("1")


style = _Style()


def echo(text: str = "", *, color: bool = True) -> None:
    """Print to stdout (Teletype-style)."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def err(text: str, *, color: bool = True) -> None:
    """Print to stderr in red (if TTY)."""
    sys.stderr.write(style.red(text, color=color) + "\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def prompt(
    question: str,
    *,
    default: Optional[str] = None,
    type: type = str,
    choices: Optional[Sequence[str]] = None,
    password: bool = False,
) -> Any:
    """Prompt the user for input on stdin."""
    suffix = f" [{default}]" if default is not None else ""
    if choices:
        suffix += f" ({'/'.join(choices)})"
    suffix += ": "
    sys.stdout.write(style.cyan("?") + f" {question}{suffix}")
    sys.stdout.flush()
    if password:
        try:
            import getpass
            raw = getpass.getpass("")
        except (ImportError, Exception):
            raw = input("")
    else:
        raw = input("")
    raw = raw.strip()
    if not raw and default is not None:
        raw = default
    if choices and raw not in choices:
        err(f"invalid choice: {raw!r} (expected one of {choices})")
        return prompt(question, default=default, type=type, choices=choices, password=password)
    return _coerce(raw, type)


def confirm(question: str, *, default: bool = False) -> bool:
    """Ask a yes/no question."""
    suffix = " [Y/n]" if default else " [y/N]"
    sys.stdout.write(style.cyan("?") + f" {question}{suffix}: ")
    sys.stdout.flush()
    raw = input("").strip().lower()
    if not raw:
        return default
    return raw in ("y", "yes", "true", "1")


# ---------------------------------------------------------------------------
# Type coercion
# ---------------------------------------------------------------------------


def _coerce(raw: str, t: Any) -> Any:
    """Coerce a string to type t, matching tiny-config's behavior."""
    if t is str or t is None:
        return raw
    if t is bool:
        return raw.lower() in ("1", "true", "yes", "y", "on", "t")
    if t is int:
        return int(raw)
    if t is float:
        return float(raw)
    if t is list or getattr(t, "__origin__", None) is list:
        inner = str if t is list else t.__args__[0]
        if not raw:
            return []
        return [_coerce(x.strip(), inner) for x in raw.split(",") if x.strip()]
    return raw


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def option(
    *flags: str,
    default: Any = ...,
    help: str = "",
    type: type = str,
    choices: Optional[Sequence[str]] = None,
) -> Any:
    """Mark a function parameter as a CLI option (flag)."""
    return {"_kind": "option", "flags": flags, "default": default, "help": help,
            "type": type, "choices": list(choices) if choices else None}


def argument(
    name: str,
    *,
    type: type = str,
    default: Any = ...,
    help: str = "",
    choices: Optional[Sequence[str]] = None,
) -> Any:
    """Mark a function parameter as a positional CLI argument."""
    return {"_kind": "argument", "name": name, "default": default, "help": help,
            "type": type, "choices": list(choices) if choices else None}


def _is_marker(x: Any) -> bool:
    return isinstance(x, dict) and "_kind" in x


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


class App:
    """Compose CLI commands with decorators."""

    def __init__(self, name: Optional[str] = None, help: Optional[str] = None, version: Optional[str] = None):
        self.name = name or Path(sys.argv[0]).stem
        self.help = help
        self.version = version
        self._commands: Dict[str, Callable[..., Any]] = {}

    def command(
        self,
        name: Optional[str] = None,
        help: Optional[str] = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a function as a subcommand."""
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            cmd_name = name or fn.__name__.replace("_", "-")
            self._commands[cmd_name] = fn
            fn.__tiny_cli_help__ = help or fn.__doc__ or ""  # type: ignore[attr-defined]
            return fn
        return deco

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=self.name,
            description=self.help,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        if self.version:
            parser.add_argument("--version", action="version", version=f"{self.name} {self.version}")
        if not self._commands:
            return parser
        subs = parser.add_subparsers(dest="cmd", metavar="<command>")
        for cmd_name, fn in self._commands.items():
            help_text = getattr(fn, "__tiny_cli_help__", "")
            sub = subs.add_parser(cmd_name, help=help_text, description=help_text,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
            sig = inspect.signature(fn)
            hints = get_type_hints(fn) if hasattr(fn, "__annotations__") else {}
            for pname, param in sig.parameters.items():
                if pname == "self":
                    continue
                t = hints.get(pname, str)
                default = param.default
                if default is inspect.Parameter.empty:
                    default = ...
                # Detect markers (set by @option/@argument)
                if _is_marker(default):
                    m = default
                    if m["_kind"] == "option":
                        if m["type"] is bool:
                            sub.add_argument(*m["flags"], action="store_true",
                                             help=m["help"],
                                             default=m["default"] if m["default"] is not ... else False)
                        else:
                            kwargs: Dict[str, Any] = {"help": m["help"], "default": m["default"]}
                            if m["default"] is ...:
                                kwargs.pop("default")
                            sub.add_argument(*m["flags"], type=_str_coerce_for_argparse(m["type"]),
                                             choices=m["choices"], **kwargs)
                    elif m["_kind"] == "argument":
                        nargs = "?" if m["default"] is not ... else None
                        sub.add_argument(m["name"], nargs=nargs, type=_str_coerce_for_argparse(m["type"]),
                                         choices=m["choices"], help=m["help"],
                                         default=m["default"] if m["default"] is not ... else None)
                else:
                    # Plain param → positional
                    if default is inspect.Parameter.empty:
                        sub.add_argument(pname, type=_str_coerce_for_argparse(t))
                    else:
                        nargs = "?"
                        sub.add_argument(pname, nargs=nargs, type=_str_coerce_for_argparse(t),
                                         default=default)
        return parser

    def run(self, argv: Optional[Sequence[str]] = None) -> int:
        """Parse argv and invoke the chosen command. Returns exit code."""
        parser = self._build_parser()
        if self._commands:
            # show help when no args
            if (argv is None and len(sys.argv) <= 1) or (argv is not None and len(argv) == 0):
                parser.print_help()
                return 0
        args = parser.parse_args(argv)
        if not self._commands:
            return 0
        cmd = getattr(args, "cmd", None)
        if cmd is None:
            parser.print_help()
            return 0
        fn = self._commands[cmd]
        sig = inspect.signature(fn)
        kwargs: Dict[str, Any] = {}
        for pname, param in sig.parameters.items():
            if pname == "self":
                continue
            if hasattr(args, pname):
                v = getattr(args, pname)
                if v is not None:
                    kwargs[pname] = v
        try:
            return int(fn(**kwargs) or 0)
        except KeyboardInterrupt:
            err("aborted")
            return 130
        except TypeError as e:
            err(f"argument error: {e}")
            return 2
        except Exception as e:
            err(f"{type(e).__name__}: {e}")
            return 1


def _str_coerce_for_argparse(t: Any) -> Any:
    """argparse wants callables that take a single string and return the value."""
    if t in (str, int, float):
        return t
    return str


from pathlib import Path  # noqa: E402  (kept at bottom to avoid a forward ref warning above)


# ---------------------------------------------------------------------------
# Test mini-app
# ---------------------------------------------------------------------------


if __name__ == "__main__":  # pragma: no cover
    app = App(name="tiny-cli-demo", help="Demo of tiny-cli")

    @app.command(help="Greet someone.")
    def greet(
        name: str,
        times: int = option("--times", "-n", default=1, type=int, help="how many times"),
        shout: bool = option("--shout", "-s", default=False, type=bool, help="uppercase"),
    ):
        msg = f"Hello, {name}!" * times
        if shout:
            msg = msg.upper()
        echo(style.green(msg))

    @app.command(help="Add two numbers.")
    def add(a: float, b: float):
        echo(style.cyan(f"{a} + {b} = {a + b}"))

    @app.command(help="Confirm a destructive action.")
    def rm(path: str, force: bool = option("--force", "-f", default=False, type=bool)):
        if not force and not confirm(f"Really delete {path}?"):
            echo("aborted")
            return
        echo(f"would remove {path}")

    sys.exit(app.run())
