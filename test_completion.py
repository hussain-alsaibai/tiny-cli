"""Tests for tiny_cli.completion (shell completion generators)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make the tiny_cli package importable from the local checkout
sys.path.insert(0, str(Path(__file__).parent))

from tiny_cli import App, option, argument
from completion import ShellCompletion


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def basic_app() -> App:
    """A simple App with two commands."""
    app = App(name="myapp", help="Test app for completion")

    @app.command(help="Greet someone")
    def greet(name: str, shout: bool = option("--shout", "-s", default=False, type=bool)):
        """Say hello."""
        return f"hi {name}"  # noqa

    @app.command(help="Add two numbers")
    def add(a: float, b: float):
        """Add two numbers."""
        return a + b

    return app


@pytest.fixture
def app_with_choices() -> App:
    """App with choices and multi-letter flags."""
    app = App(name="deploy-tool", help="Deploy things")

    @app.command(help="Deploy to an environment")
    def deploy(
        env: str = argument("env", choices=["dev", "staging", "prod"]),
        replicas: int = option("--replicas", "-r", default=1, type=int),
    ):
        return f"deploy {env}"

    return app


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_manifest_commands_present(basic_app):
    sc = ShellCompletion(basic_app)
    manifest = sc._manifest()
    names = {entry["name"] for entry in manifest}
    assert names == {"greet", "add"}


def test_manifest_help_first_line(basic_app):
    sc = ShellCompletion(basic_app)
    manifest = sc._manifest()
    greet = next(m for m in manifest if m["name"] == "greet")
    # Help text comes from @app.command(help="..."), not the docstring.
    assert greet["help"] == "Greet someone"


def test_manifest_options(basic_app):
    sc = ShellCompletion(basic_app)
    manifest = sc._manifest()
    greet = next(m for m in manifest if m["name"] == "greet")
    # shout flag is captured
    assert any("--shout" in o["flags"] for o in greet["options"])
    assert any("-s" in o["flags"] for o in greet["options"])


def test_manifest_positionals(basic_app):
    sc = ShellCompletion(basic_app)
    manifest = sc._manifest()
    greet = next(m for m in manifest if m["name"] == "greet")
    pos_names = {p["name"] for p in greet["positionals"]}
    assert "name" in pos_names


# ---------------------------------------------------------------------------
# Bash completion
# ---------------------------------------------------------------------------


def test_bash_contains_prog(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_bash()
    assert "complete -F _myapp myapp" in out


def test_bash_contains_commands(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_bash()
    assert "greet" in out
    assert "add" in out


def test_bash_contains_init_completion(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_bash()
    assert "_init_completion" in out


def test_bash_contains_option_flags(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_bash()
    assert "--shout" in out
    assert "-s" in out


def test_bash_handles_choices(app_with_choices):
    sc = ShellCompletion(app_with_choices, bind="deploy_tool")
    out = sc.emit_bash()
    assert "dev" in out
    assert "staging" in out
    assert "prod" in out


def test_bash_rejects_unknown_shell(basic_app):
    # Including an unknown shell in the constructor should raise immediately.
    with pytest.raises(ValueError):
        ShellCompletion(basic_app, shells=("bash", "zsh", "fish", "nushell"))


# ---------------------------------------------------------------------------
# Zsh completion
# ---------------------------------------------------------------------------


def test_zsh_contains_compdef(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_zsh()
    assert "#compdef myapp" in out
    assert "compdef _myapp myapp" in out


def test_zsh_contains_commands(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_zsh()
    assert "greet" in out
    assert "add" in out


def test_zsh_contains_arguments(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_zsh()
    assert "_arguments" in out
    assert "1: :->cmd" in out


def test_zsh_handles_choices(app_with_choices):
    sc = ShellCompletion(app_with_choices, bind="deploy_tool")
    out = sc.emit_zsh()
    assert "dev" in out
    assert "staging" in out


def test_zsh_handles_short_and_long_flags(app_with_choices):
    sc = ShellCompletion(app_with_choices, bind="deploy_tool")
    out = sc.emit_zsh()
    assert "--replicas" in out
    assert "-r" in out


# ---------------------------------------------------------------------------
# Fish completion
# ---------------------------------------------------------------------------


def test_fish_contains_subcommand_completions(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_fish()
    assert "complete -c myapp" in out
    assert "greet" in out
    assert "add" in out


def test_fish_contains_long_flag(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_fish()
    assert "--shout" in out or "-l shout" in out


def test_fish_contains_short_flag(basic_app):
    sc = ShellCompletion(basic_app)
    out = sc.emit_fish()
    assert " -s shout" in out or " -s s" in out


def test_fish_handles_choices(app_with_choices):
    sc = ShellCompletion(app_with_choices, bind="deploy_tool")
    out = sc.emit_fish()
    assert "dev" in out
    assert "staging" in out
    assert "prod" in out


def test_fish_bool_flag_no_r(basic_app):
    """Boolean flags should not take a value."""
    sc = ShellCompletion(basic_app)
    out = sc.emit_fish()
    # Find the line for --shout and ensure it doesn't have -r
    lines_with_shout = [ln for ln in out.splitlines() if "shout" in ln]
    assert lines_with_shout
    # None of the shout lines should have -r (require-value) immediately followed by shout
    bad = [ln for ln in lines_with_shout if " -r " in ln]
    assert not bad, f"bool flag should not require a value: {bad}"


# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------


def test_install_bash(tmp_path):
    app = App(name="mytool")
    @app.command()
    def cmd():
        return None

    sc = ShellCompletion(app, bind="mytool")
    out_path = sc.install("bash", dest_dir=tmp_path)
    assert out_path.exists()
    assert out_path.read_text().startswith("# bash completion for mytool")


def test_install_zsh(tmp_path):
    app = App(name="mytool")
    @app.command()
    def cmd():
        return None

    sc = ShellCompletion(app, bind="mytool")
    out_path = sc.install("zsh", dest_dir=tmp_path)
    assert out_path.exists()
    assert out_path.name.startswith("_")
    assert "#compdef mytool" in out_path.read_text()


def test_install_fish(tmp_path):
    app = App(name="mytool")
    @app.command()
    def cmd():
        return None

    sc = ShellCompletion(app, bind="mytool")
    out_path = sc.install("fish", dest_dir=tmp_path)
    assert out_path.exists()
    assert out_path.name.endswith(".fish")


def test_install_no_overwrite(tmp_path):
    app = App(name="mytool")
    @app.command()
    def cmd():
        return None

    sc = ShellCompletion(app, bind="mytool")
    sc.install("bash", dest_dir=tmp_path)
    # Second install without overwrite should fail
    with pytest.raises(FileExistsError):
        sc.install("bash", dest_dir=tmp_path)
    # With overwrite=True it should succeed
    sc.install("bash", dest_dir=tmp_path, overwrite=True)


def test_install_unsupported_shell(tmp_path):
    app = App(name="mytool")
    @app.command()
    def cmd():
        return None

    sc = ShellCompletion(app, bind="mytool")
    with pytest.raises(ValueError):
        sc.install("powershell", dest_dir=tmp_path)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def test_emit_dispatch(basic_app):
    sc = ShellCompletion(basic_app)
    assert sc.emit("bash").startswith("# bash completion")
    assert sc.emit("zsh").startswith("#compdef")
    assert sc.emit("fish").startswith("# fish completion")


def test_emit_unknown_shell(basic_app):
    sc = ShellCompletion(basic_app)
    with pytest.raises(ValueError):
        sc.emit("elvish")


# ---------------------------------------------------------------------------
# Integration: end-to-end with a real App
# ---------------------------------------------------------------------------


def test_integration_app_with_group_and_async(basic_app):
    """Smoke test: a more realistic app structure."""
    app = App(name="bigtool", help="A bigger test app")

    @app.command(help="Sync command")
    def sync(path: str):
        return f"sync {path}"

    @app.command(help="Async command")
    async def fetch(url: str = option("--url", "-u", default="")):
        return f"fetch {url}"

    sc = ShellCompletion(app)
    bash_out = sc.emit_bash()
    zsh_out = sc.emit_zsh()
    fish_out = sc.emit_fish()
    assert "sync" in bash_out and "fetch" in bash_out
    assert "sync" in zsh_out and "fetch" in zsh_out
    assert "sync" in fish_out and "fetch" in fish_out
    assert "--url" in bash_out
