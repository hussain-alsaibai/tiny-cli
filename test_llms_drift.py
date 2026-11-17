"""Doc-drift guard for tiny-cli's llms.txt.

`llms.txt` is what an agent reads before choosing the library. Nothing built
it or checked it, so on 2026-11-17 it advertised:

  - `Version: 1.1.0` against a package at 1.3.1
  - `Python (3.8+)` against `requires-python = ">=3.9"` in pyproject.toml
  - a hand-written example using `@cli.option(...)` as a decorator; `option`
    is a default-value marker, and `required=` does not exist, so the
    documented first example raised `AttributeError: 'App' object has no
    attribute 'option'` on the very first line a new user copies
  - no mention of `from_module`, `command_from`, `Progress`, `Spinner`,
    `confirm`, or `load_env`, all shipped in 1.2.0/1.1.0

The example test below executes the snippet out of the file, which is the
only assertion that catches a decorator typo.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import tiny_cli as tc

ROOT = Path(__file__).parent

# Run snippets from a temp dir with the repo importable. A subprocess started
# from tmp_path puts tmp_path on sys.path, not the repo.
_ENV = {**os.environ, "PYTHONPATH": str(ROOT)}
LLMS = ROOT / "llms.txt"
PYPROJECT = ROOT / "pyproject.toml"

# Each name is exported by `tiny_cli` today; test_listed_names_are_real proves
# it rather than trusting this list.
DOCUMENTED_API = [
    "App", "echo", "err", "status", "style", "option", "argument",
    "Table", "Tree", "Progress", "Spinner", "prompt", "confirm", "load_env",
]


def _text() -> str:
    assert LLMS.is_file(), "llms.txt is missing"
    return LLMS.read_text(encoding="utf-8")


def _pyproject_version() -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert m, "pyproject.toml has no [project].version"
    return m.group(1)


def _python_floor() -> str:
    m = re.search(r'^requires-python\s*=\s*"([^"]+)"', PYPROJECT.read_text(encoding="utf-8"), re.M)
    assert m, "pyproject.toml has no requires-python"
    return m.group(1).lstrip(">=~^ ")


def test_version_header_matches_pyproject():
    m = re.search(r"^- Version:\s*(\S+)\s*$", _text(), re.M)
    assert m, "llms.txt has no '- Version:' line"
    assert m.group(1) == _pyproject_version(), (
        f"llms.txt says {m.group(1)}, pyproject.toml says {_pyproject_version()}"
    )


def test_header_matches_module_and_pyproject():
    header = re.search(r"^- Version:\s*(\S+)\s*$", _text(), re.M).group(1)
    assert header == tc.__version__ == _pyproject_version()


def test_python_floor_matches_pyproject():
    m = re.search(r"^- Language:\s*Python \(([^)]+)\)", _text(), re.M)
    assert m, "llms.txt has no '- Language: Python (...)' line"
    assert m.group(1).rstrip("+") == _python_floor(), (
        f"llms.txt claims Python {m.group(1)}, requires-python is {_python_floor()}"
    )


@pytest.mark.parametrize("name", DOCUMENTED_API)
def test_documented_api_present(name):
    assert re.search(rf"\b{re.escape(name)}\b", _text()), (
        f"llms.txt never mentions `{name}`, which this version exports"
    )


@pytest.mark.parametrize("name", DOCUMENTED_API)
def test_listed_names_are_real(name):
    assert hasattr(tc, name), (
        f"llms.txt documents `{name}` but `tiny_cli` does not export it"
    )


def test_advertised_install_line_is_correct():
    """The PyPI name belongs to another project; the docs must say so."""
    text = _text()
    assert "git+https://github.com/hussain-alsaibai/tiny-cli" in text
    assert "pip install tiny-cli" in text, (
        "the warning about the colliding PyPI name was removed"
    )


def _section(name: str) -> str:
    """Return the text of a `## name` section, up to the next `## `."""
    text = _text()
    marker = f"## {name}"
    assert marker in text, f"llms.txt has no '{marker}' section"
    return text.split(marker, 1)[1].split("\n## ", 1)[0]


def _minimal_example() -> str:
    m = re.search(r"```python\n(.*?)```", _section("Minimal example"), re.S)
    assert m, "the 'Minimal example' section has no python block"
    return m.group(1)


def test_minimal_example_runs(tmp_path):
    """Execute the documented snippet. A decorator typo fails here, not at import."""
    src = _minimal_example()
    f = tmp_path / "example.py"
    f.write_text(src, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(f), "add", "hello", "--tag", "work"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60, env=_ENV,
    )
    assert r.returncode == 0, f"documented example exited {r.returncode}:\n{r.stderr}"
    assert "[work] hello" in r.stdout, f"unexpected output: {r.stdout!r}"


def test_minimal_example_json_mode(tmp_path):
    src = _minimal_example()
    f = tmp_path / "example.py"
    f.write_text(src, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(f), "add", "hello", "--tag", "work", "--json"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60, env=_ENV,
    )
    assert r.returncode == 0, r.stderr
    import json
    env = json.loads(r.stdout)
    assert "_kind" not in r.stdout, "a marker dict leaked into the JSON envelope"
    assert env["exit_code"] == 0


def test_json_contract_example_runs(tmp_path):
    """The JSON-contract snippet must be executable, not just plausible.

    The snippet is a fragment (a decorated command, no `cli.run()`), so it is
    wrapped in a harness that supplies the App and calls run(). The assertion
    that matters is that a parameter whose flag name differs from its
    parameter name still reaches the command - the 1.3.2 bug - because the
    snippet deliberately uses `--user` on `user_id`.
    """
    m = re.search(r"```python\n(.*?)```", _section("The JSON contract"), re.S)
    assert m, "the 'JSON contract' section has no python block"
    snippet = m.group(1)

    harness = (
        "import tiny_cli as tc\n"
        "app = tc.App('t')\n\n"
        + snippet.rstrip()
        + "\n\napp.run()\n"
    )
    h = tmp_path / "h.py"
    h.write_text(harness, encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(h), "show", "--user", "7", "--json"],
        capture_output=True, text=True, cwd=str(ROOT), timeout=60, env=_ENV,
    )
    assert r.returncode == 0, r.stderr
    import json
    env = json.loads(r.stdout)
    assert env["result"]["id"] == "7", env
    assert "_kind" not in r.stdout, r.stdout
