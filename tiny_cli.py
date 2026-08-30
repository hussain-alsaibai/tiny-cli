"""tiny-cli: Zero-dependency CLI builder for Python.

Compose command-line interfaces with decorators, type coercion, color output,
prompts, progress bars, JSON output, tree rendering, auto-env loading, and
shell completion. argparse replacement for the 90% case — and a first-class
target for AI agents, scripts, and CI.

Single file, no deps, MIT, fully typed.

Example:
    @app.command()
    def greet(name: str, times: int = 1, shout: bool = False):
        '''Say hello.'''
        msg = f"Hello, {name}!" * times
        if shout:
            msg = msg.upper()
        echo(msg)

    app.run()
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import shlex
import sys
import textwrap
import threading
import time
from pathlib import Path
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

__version__ = "1.1.0"

# Exit code constants (POSIX-friendly + signal-derived)
OK = 0
ERROR = 1
USAGE = 2
INTERNAL = 3
ABORT = 130  # SIGINT

__all__ = [
    "App",
    "command",
    "option",
    "argument",
    "confirm",
    "prompt",
    "echo",
    "err",
    "style",
    "Progress",
    "Spinner",
    "Table",
    "Tree",
    "status",
    "OK",
    "ERROR",
    "USAGE",
    "INTERNAL",
    "ABORT",
]


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

def _echo_internal(text: str = "") -> None:
    """Internal echo used by App.run() — bypasses JSON-mode suppression."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


def err(text: str, *, color: bool = True) -> None:
    """Print to stderr in red (if TTY)."""
    sys.stderr.write(style.red(text, color=color) + "\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# .env loader (stdlib-only)
# ---------------------------------------------------------------------------


def _parse_env_file(path: Union[str, Path]) -> Dict[str, str]:
    """Parse a .env file manually as KEY=VALUE lines.

    - Ignores blank lines and lines starting with '#'.
    - Strips optional 'export ' prefix.
    - Supports double- or single-quoted values with escape sequences.
    - Does not override existing environment variables unless override=True.
    """
    result: Dict[str, str] = {}
    p = Path(path)
    if not p.exists() or not p.is_file():
        return result
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return result
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip optional surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
            if value[0] == '"':
                # Minimal escape processing for double quotes
                value = value.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")
        result[key] = value
    return result


def load_env(path: Union[str, Path] = ".env", *, override: bool = False) -> Dict[str, str]:
    """Load a .env file into os.environ.

    Returns the dict of values that were (or would have been) set.
    """
    values = _parse_env_file(path)
    for k, v in values.items():
        if override or k not in os.environ:
            os.environ[k] = v
    return values


# ---------------------------------------------------------------------------
# Progress bar, spinner, status
# ---------------------------------------------------------------------------


class Progress:
    """ASCII progress bar for CLI operations.

    Usage:
        p = Progress(total=100, desc="Downloading")
        for i in p.iter(range(100)):
            time.sleep(0.01)
        p.close()
    """

    _BARS = ["#", ">"]

    def __init__(
        self,
        total: int | None = None,
        desc: str = "",
        width: int = 24,
        show_percent: bool = True,
        show_count: bool = False,
    ) -> None:
        self.total = total
        self.current = 0
        self.desc = desc
        self.width = width
        self.show_percent = show_percent
        self.show_count = show_count
        self._closed = False
        self._last_len = 0

    def update(self, n: int = 1) -> None:
        self.current = min(n, self.total if self.total else n)
        if not self._closed:
            self._render()

    def iter(self, iterable: Iterable[Any]) -> Iterable[Any]:
        """Iterate with auto-progress. Total is inferred from len(iterable)."""
        it = iter(iterable)
        if self.total is None:
            try:
                self.total = len(iterable)  # type: ignore
            except TypeError:
                pass
        for item in it:
            yield item
            self.update(self.current + 1)
        self.close()

    def _render(self) -> None:
        if self.total and self.total <= 0:
            return
        pct = self.current / self.total if (self.total and self.total > 0) else 0.0
        filled = int(pct * self.width)
        bar = (
            f"{'█' * filled}{'░' * (self.width - filled)}"
            if sys.stderr.isatty()
            else f"[{filled}/{self.width}]"
        )
        parts = [bar]
        if self.show_percent:
            parts.append(f"{pct * 100:.0f}%")
        if self.show_count and self.total:
            parts.append(f"{self.current}/{self.total}")
        info = " ".join(parts)
        line = f"\r{self.desc}: {info}" if self.desc else f"{info}"
        sys.stderr.write(line + " " * max(0, self._last_len - len(line)))
        sys.stderr.flush()
        self._last_len = len(line)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sys.stderr.write("\n")
        sys.stderr.flush()
        self._last_len = 0

    def __enter__(self) -> "Progress":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class Spinner:
    """Animated spinner for long-running operations.

    Usage:
        with Spinner("Working"):
            time.sleep(2)
    """

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, desc: str = "", interval_ms: int = 80) -> None:
        self.desc = desc
        self.interval_ms = interval_ms
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._msg = ""

    def set_message(self, msg: str) -> None:
        """Update the message shown next to the spinner."""
        self._msg = f" {msg}" if msg else ""

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            line = f"\r{style.cyan(frame, color=True)} {self.desc}{self._msg}"
            sys.stderr.write(line)
            sys.stderr.flush()
            i += 1
            self._stop.wait(self.interval_ms / 1000.0)
        sys.stderr.write("\r" + " " * 60 + "\r")
        sys.stderr.flush()

    def start(self) -> "Spinner":
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)

    def __enter__(self) -> "Spinner":
        return self.start()

    def __exit__(self, *_: Any) -> None:
        self.stop()


def status(msg: str, ok: bool = True) -> None:
    """Print a one-liner status: ✓ msg or ✗ msg."""
    mark = style.green("✓") if ok else style.red("✗")
    sys.stderr.write(f"{mark} {msg}\n")
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Tree renderer
# ---------------------------------------------------------------------------


class Tree:
    """ASCII tree renderer for directory/file hierarchies.

    Usage:
        t = Tree(root_label="myproject/")
        t.add("src/", "dir")
        t.add("src/main.py", "file")
        t.add("README.md", "file")
        t.add("src/utils.py", "file")
        print(t)

    Auto-detects TTY for Unicode box drawing vs ASCII fallback.

    Symbols:
        ├  ─  │  └   (Unicode when stdout is a TTY)
        |  -  |  `   (ASCII fallback for pipes/log files)
    """

    # Branch glyphs: (branch, last, vertical, horizontal, space, root_marker)
    GLYPHS_UNICODE = {
        "branch": "├",
        "last": "└",
        "vertical": "│",
        "horizontal": "─",
        "space": "  ",
        "root": "──",
    }
    GLYPHS_ASCII = {
        "branch": "|--",
        "last": "`--",
        "vertical": "|",
        "horizontal": "-",
        "space": "   ",
        "root": "---",
    }

    def __init__(self, root_label: str = "") -> None:
        self.root_label = root_label
        # Internal storage: list of (depth, path, type, children)
        # We'll use a simpler flat-list approach: each `add` registers a path,
        # and __str__ builds the tree by inferring parent/child relationships.
        self._entries: List[Tuple[str, str]] = []  # list of (path, type)
        self._ascii = not sys.stdout.isatty()

    def set_ascii(self, ascii_mode: bool) -> "Tree":
        """Force ASCII glyphs (useful for log files / non-TTY output)."""
        self._ascii = bool(ascii_mode)
        return self

    def add(self, path: str, type: str = "file") -> "Tree":
        """Add an entry to the tree.

        type is one of "file", "dir", "link". Use "dir" for branches.
        """
        if type not in ("file", "dir", "link"):
            type = "file"
        self._entries.append((path, type))
        return self

    def _glyphs(self) -> Dict[str, str]:
        return self.GLYPHS_ASCII if self._ascii else self.GLYPHS_UNICODE

    @staticmethod
    def _split(path: str) -> List[str]:
        # Normalize: strip leading/trailing slashes, treat as path segments
        return [p for p in path.replace("\\", "/").strip("/").split("/") if p]

    def _build_tree(self) -> Tuple[Dict[str, Any], List[str]]:
        """Build a nested tree structure from flat entries.

        Returns (root_dict, roots_list). Each node is a dict:
            {"name": str, "type": str, "children": {name: node, ...}}
        """
        root: Dict[str, Any] = {"name": "", "type": "dir", "children": {}}
        for path, type_ in self._entries:
            parts = self._split(path)
            if not parts:
                continue
            cur = root
            for i, part in enumerate(parts):
                is_last = i == len(parts) - 1
                if part not in cur["children"]:
                    cur["children"][part] = {
                        "name": part,
                        "type": type_ if is_last else "dir",
                        "children": {},
                    }
                cur = cur["children"][part]
                # If a previous entry declared this as a "file" but a later
                # entry has it as a parent, upgrade to "dir".
                if not is_last and cur["type"] == "file":
                    cur["type"] = "dir"
        # Roots: top-level children, in insertion order
        return root, list(root["children"].keys())

    def __str__(self) -> str:
        lines: List[str] = []
        g = self._glyphs()

        # Root label (optional)
        if self.root_label:
            lines.append(self.root_label)

        root, top_keys = self._build_tree()
        top_nodes = [root["children"][k] for k in top_keys]

        def render_node(node: Dict[str, Any], prefix: str, is_last: bool, is_root: bool) -> List[str]:
            """Render a single node + descendants. prefix is the branch prefix from the parent's level."""
            out: List[str] = []
            if is_root:
                # Top-level node: no branch glyph, just the name
                out.append(node["name"] + ("/" if node["type"] == "dir" else ""))
            else:
                glyph = g["last"] if is_last else g["branch"]
                out.append(f"{prefix}{glyph} {node['name']}" + ("/" if node["type"] == "dir" else ""))
            child_keys = list(node["children"].keys())
            # New prefix for children
            if is_root:
                # First level: no parent branch
                new_prefix = ""
            else:
                new_prefix = prefix + (g["space"] if is_last else g["vertical"] + " ")
            for i, ck in enumerate(child_keys):
                child = node["children"][ck]
                out.extend(render_node(child, new_prefix, i == len(child_keys) - 1, False))
            return out

        for i, node in enumerate(top_nodes):
            lines.extend(render_node(node, "", i == len(top_nodes) - 1, True))

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Table renderer (with themes + filtering + sorting)
# ---------------------------------------------------------------------------


class Table:
    """ASCII table renderer with multiple themes.

    Usage:
        t = Table(["Name", "Type", "Size"], theme="markdown")
        t.add_row("tiny-cli", "CLI", "8 KB")
        t.add_row("tiny-log", "Logging", "12 KB")
        t.sort_by("Size", reverse=True)
        t.filter_cols("Name", "Size")
        print(t)

    Themes:
        "box"      — Unicode box-drawing (┌ ┐ │ ─ etc.) [default]
        "simple"   — ASCII '-' separators only
        "markdown" — GitHub-flavored pipe table
    """

    def __init__(
        self,
        headers: Sequence[str],
        align: Sequence[str] | None = None,
        theme: str = "box",
    ) -> None:
        if theme not in ("box", "simple", "markdown"):
            theme = "box"
        self.headers = list(headers)
        self.rows: List[List[str]] = []
        self._widths = [len(h) for h in self.headers]
        self._align = list(align) if align else ["l"] * len(self.headers)
        self.theme = theme

    def add_row(self, *cells: str) -> "Table":
        cells_list = [str(c) for c in cells]
        while len(cells_list) < len(self.headers):
            cells_list.append("")
        self.rows.append(cells_list)
        for i, cell in enumerate(cells_list):
            self._widths[i] = max(self._widths[i], len(cell))
        return self

    def filter_cols(self, *names: str) -> "Table":
        """Keep only the named columns (in the given order)."""
        keep_idx: List[int] = []
        for name in names:
            if name in self.headers:
                keep_idx.append(self.headers.index(name))
        if not keep_idx:
            return self
        self.headers = [self.headers[i] for i in keep_idx]
        self._widths = [self._widths[i] for i in keep_idx]
        self._align = [self._align[i] for i in keep_idx]
        self.rows = [[row[i] for i in keep_idx] for row in self.rows]
        return self

    def sort_by(self, col_name: str, reverse: bool = False) -> "Table":
        """Sort rows by a column. Values are compared as strings (natural order)."""
        if col_name not in self.headers:
            return self
        idx = self.headers.index(col_name)

        def sort_key(row: List[str]) -> str:
            return row[idx] if idx < len(row) else ""

        self.rows.sort(key=sort_key, reverse=reverse)
        return self

    def _format_cell(self, value: str, width: int, align: str) -> str:
        s = str(value)
        if align == "r":
            return s.rjust(width)
        if align == "c":
            return s.center(width)
        return s.ljust(width)

    def __str__(self) -> str:
        lines: List[str] = []
        if self.theme == "markdown":
            sep = "|"
            pad = " "
            # Header
            lines.append(
                sep + sep.join(
                    pad + self._format_cell(h, w, "l") + pad for h, w in zip(self.headers, self._widths)
                ) + sep
            )
            # Markdown separator: | --- | --- |
            lines.append(
                sep + sep.join(
                    pad + "-" * max(3, w) + pad for w in self._widths
                ) + sep
            )
            # Body
            for row in self.rows:
                padded = list(row) + [""] * (len(self.headers) - len(row))
                lines.append(
                    sep + sep.join(
                        pad + self._format_cell(padded[i], self._widths[i], self._align[i]) + pad
                        for i in range(len(self.headers))
                    ) + sep
                )
        elif self.theme == "simple":
            sep = " "
            # Header
            lines.append(
                " ".join(
                    self._format_cell(h, w, "l") for h, w in zip(self.headers, self._widths)
                )
            )
            lines.append(" ".join("-" * w for w in self._widths))
            # Body
            for row in self.rows:
                padded = list(row) + [""] * (len(self.headers) - len(row))
                lines.append(
                    sep.join(
                        self._format_cell(padded[i], self._widths[i], self._align[i])
                        for i in range(len(self.headers))
                    )
                )
        else:  # "box" — default
            sep = " │ "
            border = "┌" + "┬".join("─" * w for w in self._widths) + "┐"
            divider = "├" + "┼".join("─" * w for w in self._widths) + "┤"
            bottom = "└" + "┴".join("─" * w for w in self._widths) + "┘"
            lines.append(border)
            lines.append(
                "│" + sep.join(
                    f" {self._format_cell(self.headers[i], self._widths[i], self._align[i])} │"
                    for i in range(len(self.headers))
                )
            )
            lines.append(divider)
            for row in self.rows:
                padded = list(row) + [""] * (len(self.headers) - len(row))
                lines.append(
                    "│" + sep.join(
                        f" {self._format_cell(padded[i], self._widths[i], self._align[i])} │"
                        for i in range(len(self.headers))
                    )
                )
            lines.append(bottom)
        return "\n".join(lines)


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
    """Compose CLI commands with decorators.

    New in v1.1.0:
        auto_env=True        — auto-load .env (or a custom path) from cwd
        output_mode="text"   — default; human-readable output
        output_mode="json"   — single JSON envelope on stdout, errors on stderr
        output_mode="silent" — only echo() to stdout, everything else to stderr
        set_banner(text)     — banner shown on --help and at startup
        set_logo(lines)      — ASCII/Unicode logo lines shown above the banner
    """

    def __init__(
        self,
        name: Optional[str] = None,
        help: Optional[str] = None,
        version: Optional[str] = None,
        auto_env: Union[bool, str] = False,
        env_path: Optional[Union[str, Path]] = None,
    ):
        self.name = name or Path(sys.argv[0]).stem
        self.help = help
        self.version = version
        self._commands: Dict[str, Callable[..., Any]] = {}
        # v1.1.0 additions
        self._banner: Optional[str] = None
        self._logo: Optional[List[str]] = None
        self._auto_env = auto_env
        self._env_path = env_path

        # Resolve output_mode from explicit param, env var, or --json flag.
        env_json = os.environ.get("TINY_CLI_JSON") == "1"
        cli_json = "--json" in sys.argv[1:]
        if env_json or cli_json:
            self.output_mode: str = "json"
        else:
            self.output_mode = "text"

        # Auto-load .env if requested
        if self._auto_env:
            path = self._env_path
            if isinstance(self._auto_env, str) and self._auto_env:
                path = self._auto_env
            if path is None:
                path = ".env"
            load_env(path)

    # ---- Banner / logo ------------------------------------------------

    def set_banner(self, text: str) -> "App":
        """Set the banner text shown on --help and at startup.

        Banner is only printed when TINY_CLI_SHOW_BANNER=1 or --show-banner is passed.
        """
        self._banner = text
        return self

    def set_logo(self, lines: List[str]) -> "App":
        """Set the logo lines printed above the banner."""
        self._logo = list(lines)
        return self

    def _print_banner(self, *, to_stderr: bool = False) -> None:
        """Print logo + banner. Suppressed in JSON/silent output modes."""
        if self.output_mode != "text":
            return
        out = sys.stderr if to_stderr else sys.stdout
        if self._logo:
            for line in self._logo:
                out.write(line + "\n")
        if self._banner:
            out.write(self._banner + "\n")
        if self._logo or self._banner:
            out.flush()

    # ---- Command registration -----------------------------------------

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

    # ---- Parser construction ------------------------------------------

    def _build_parser(self, *, include_global_json: bool = False) -> argparse.ArgumentParser:
        # Use RawDescriptionHelpFormatter so banner text in description
        # is preserved. We append banner to description at print_help() time.
        parser = argparse.ArgumentParser(
            prog=self.name,
            description=self.help,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        if self.version:
            parser.add_argument("--version", action="version", version=f"{self.name} {self.version}")
        # Global --json flag: only added at parse-time so it doesn't pollute
        # --help when the user hasn't opted in. We detect it via the raw
        # argv in run() and remove it before parse_args().
        if include_global_json:
            parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
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

    # ---- JSON output helpers ------------------------------------------

    def _emit_json(
        self,
        *,
        command: Optional[str],
        args: Optional[Dict[str, Any]],
        result: Any = None,
        error: Optional[str] = None,
        exit_code: int = 0,
    ) -> None:
        """Emit a single JSON envelope describing the command run."""
        # Best-effort serialization: fall back to repr for unknown types.
        def safe(v: Any) -> Any:
            if isinstance(v, (str, int, float, bool)) or v is None:
                return v
            if isinstance(v, (list, tuple)):
                return [safe(x) for x in v]
            if isinstance(v, dict):
                return {str(k): safe(x) for k, x in v.items()}
            return repr(v)

        payload = {
            "command": str(command) if command else None,
            "args": safe(args) if args else None,
            "result": safe(result),
            "error": error,
            "exit_code": int(exit_code),
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    # ---- Main entry point ---------------------------------------------

    def run(self, argv: Optional[Sequence[str]] = None) -> int:
        """Parse argv and invoke the chosen command. Returns exit code."""
        # Strip tiny-cli-specific flags before delegating to argparse
        # so they don't show up in --help as unknown options.
        if argv is None:
            argv = list(sys.argv[1:])
        else:
            argv = list(argv)

        # Pull --json out of argv so argparse doesn't choke on it.
        json_flag = False
        if "--json" in argv:
            json_flag = True
            argv = [a for a in argv if a != "--json"]
        # Same for --show-banner.
        show_banner = (
            os.environ.get("TINY_CLI_SHOW_BANNER") == "1"
            or "--show-banner" in argv
        )
        if "--show-banner" in argv:
            argv = [a for a in argv if a != "--show-banner"]

        # If --json was passed, flip into JSON output mode for this run.
        if json_flag:
            self.output_mode = "json"

        if show_banner and not argv:
            self._print_banner()
            return OK

        parser = self._build_parser(include_global_json=json_flag)

        # When no args and no commands, show help + banner
        if not argv and not self._commands:
            self._print_banner()
            parser.print_help()
            return OK
        if self._commands and not argv:
            # Show banner above help if requested
            self._print_banner()
            if self.output_mode == "json":
                # Emit JSON help envelope instead of plain text
                import io as _io
                buf = _io.StringIO()
                parser.print_help(buf)
                self._emit_json(
                    command=None,
                    args=None,
                    result={"help": buf.getvalue()},
                    error=None,
                    exit_code=OK,
                )
                return OK
            parser.print_help()
            return OK

        # Parse — wrap errors as JSON if needed
        try:
            args = parser.parse_args(argv)
        except SystemExit as e:
            # argparse calls sys.exit on parse errors / --help
            code = int(e.code) if e.code is not None else 0
            if self.output_mode == "json":
                if code == 0:
                    # --help in JSON mode: emit a help envelope
                    import io as _io
                    buf = _io.StringIO()
                    parser.print_help(buf)
                    self._emit_json(
                        command=None,
                        args=None,
                        result={"help": buf.getvalue()},
                        error=None,
                        exit_code=OK,
                    )
                else:
                    self._emit_json(
                        command=None,
                        args=None,
                        result=None,
                        error=f"parse error (exit {code})",
                        exit_code=code or USAGE,
                    )
            return code if code != 0 else OK

        if not self._commands:
            return OK

        cmd = getattr(args, "cmd", None)
        if cmd is None:
            self._print_banner()
            parser.print_help()
            return OK
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
            # In JSON mode, suppress echo() so user commands don't pollute
            # stdout. The user is expected to return their data from the
            # command function instead. We patch both the module global
            # (used by the bundled demo) and the tiny_cli.echo attribute
            # (used by code that imports tiny_cli as `tc`).
            if self.output_mode == "json":
                _self_module = sys.modules[__name__]
                original_module_echo = _self_module.echo

                def _suppressed_echo(text: str = "", *, color: bool = True) -> None:
                    pass

                globals()["echo"] = _suppressed_echo
                _self_module.echo = _suppressed_echo
            try:
                result = fn(**kwargs)
                rc = int(result) if result is not None else OK
            finally:
                if self.output_mode == "json":
                    _self_module = sys.modules[__name__]
                    globals()["echo"] = _self_module.echo
                    _self_module.echo = original_module_echo
        except KeyboardInterrupt:
            err_msg = "aborted"
            if self.output_mode == "json":
                self._emit_json(command=cmd, args=kwargs, result=None,
                                error=err_msg, exit_code=ABORT)
            else:
                err(err_msg)
            return ABORT
        except TypeError as e:
            if self.output_mode == "json":
                self._emit_json(command=cmd, args=kwargs, result=None,
                                error=f"argument error: {e}", exit_code=USAGE)
            else:
                err(f"argument error: {e}")
            return USAGE
        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            if self.output_mode == "json":
                self._emit_json(command=cmd, args=kwargs, result=None,
                                error=err_msg, exit_code=ERROR)
            else:
                err(err_msg)
            return ERROR

        if self.output_mode == "json":
            self._emit_json(command=cmd, args=kwargs, result=result, error=None,
                            exit_code=rc)
        return rc


def _str_coerce_for_argparse(t: Any) -> Any:
    """argparse wants callables that take a single string and return the value."""
    if t in (str, int, float):
        return t
    return str


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
