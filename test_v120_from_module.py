"""v1.2.0 — Tests for App.from_module and App.command_from."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault("TINY_CLI_FORCE_COLOR", "1")
os.environ.pop("TINY_CLI_JSON", None)
import tiny_cli as tc  # noqa: E402


def _make_module(name, source, tmpdir=None):
    """Write a Python module file and return the loaded module object."""
    cleanup_dir = None
    if tmpdir is None:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        tmp.write(source)
        tmp.close()
        path = tmp.name
    else:
        path = os.path.join(tmpdir, f"{name}.py")
        with open(path, "w") as f:
            f.write(source)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, path


class TestFromModule(unittest.TestCase):
    def test_only_decorated_true_default(self) -> None:
        mod, path = _make_module("tcm1", '''
def public_no_doc():
    return 0

def decorated_cmd():
    return 0
decorated_cmd.__tiny_cli_help__ = "Already decorated."
''')
        try:
            app = tc.App.from_module(mod)
            self.assertEqual(sorted(app._commands.keys()), ["decorated-cmd"])
        finally:
            os.unlink(path)

    def test_only_decorated_false_includes_all_public(self) -> None:
        mod, path = _make_module("tcm2", '''
def foo():
    return 0

def bar():
    return 0

def _private():
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            self.assertEqual(sorted(app._commands.keys()), ["bar", "foo"])
        finally:
            os.unlink(path)

    def test_skips_imported_functions(self) -> None:
        """Functions whose __module__ is not the target module are skipped."""
        mod, path = _make_module("tcm3", '''
from os import path  # imported, not defined here

def local_func():
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            # 'path' is imported from os so __module__ is 'os' — should be skipped.
            self.assertIn("local-func", app._commands)
            self.assertNotIn("path", app._commands)
        finally:
            os.unlink(path)

    def test_prefix(self) -> None:
        mod, path = _make_module("tcm4", '''
def foo():
    return 0
def bar():
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False, prefix="aws")
            self.assertIn("aws-foo", app._commands)
            self.assertIn("aws-bar", app._commands)
        finally:
            os.unlink(path)

    def test_underscore_to_dash_in_command_name(self) -> None:
        mod, path = _make_module("tcm5", '''
def my_long_command():
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            self.assertIn("my-long-command", app._commands)
        finally:
            os.unlink(path)

    def test_help_text_from_docstring(self) -> None:
        mod, path = _make_module("tcm6", '''
def cmd_with_doc():
    """This is the help text."""
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            fn = app._commands["cmd-with-doc"]
            self.assertEqual(fn.__tiny_cli_help__, "This is the help text.")
        finally:
            os.unlink(path)

    def test_app_name_from_module_basename(self) -> None:
        mod, path = _make_module("mycommands", '''
def foo():
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            self.assertEqual(app.name, "mycommands")
        finally:
            os.unlink(path)

    def test_app_help_from_module_docstring(self) -> None:
        mod, path = _make_module("tcm7", '''
"""Module-level help text."""

def foo():
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            self.assertEqual(app.help, "Module-level help text.")
        finally:
            os.unlink(path)

    def test_string_path_imports(self) -> None:
        tmpdir = tempfile.mkdtemp()
        try:
            pkg = os.path.join(tmpdir, "myapp_xx1")
            os.makedirs(pkg)
            open(os.path.join(pkg, "__init__.py"), "w").close()
            with open(os.path.join(pkg, "cmds.py"), "w") as f:
                f.write('def hello():\n    print("hi")\n    return 0\n')
            sys.path.insert(0, tmpdir)
            try:
                app = tc.App.from_module("myapp_xx1.cmds", only_decorated=False)
                self.assertIn("hello", app._commands)
            finally:
                sys.path.remove(tmpdir)
        finally:
            import shutil
            shutil.rmtree(tmpdir)

    def test_actually_run_discovered_command(self) -> None:
        mod, path = _make_module("tcm9", '''
def hello(name):
    print("hi " + name)
    return 0
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            out = StringIO()
            err = StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                rc = app.run(argv=["hello", "world"])
            self.assertEqual(rc, 0, f"rc={rc} stderr={err.getvalue()!r}")
            self.assertIn("hi world", out.getvalue())
        finally:
            os.unlink(path)

    def test_empty_module(self) -> None:
        mod, path = _make_module("tcm10", '''
"""Empty."""
''')
        try:
            app = tc.App.from_module(mod, only_decorated=False)
            self.assertEqual(app._commands, {})
        finally:
            os.unlink(path)


class TestCommandFrom(unittest.TestCase):
    def test_command_from_function(self) -> None:
        def external():
            return 0
        app = tc.App(name="t11")
        app.command_from(external)
        self.assertIn("external", app._commands)

    def test_command_from_custom_name(self) -> None:
        def fn():
            return 0
        app = tc.App(name="t12")
        app.command_from(fn, name="renamed")
        self.assertIn("renamed", app._commands)
        self.assertNotIn("fn", app._commands)

    def test_command_from_docstring_becomes_help(self) -> None:
        def fn():
            """External docstring."""
            return 0
        app = tc.App(name="t13")
        app.command_from(fn)
        self.assertEqual(app._commands["fn"].__tiny_cli_help__, "External docstring.")

    def test_command_from_does_not_overwrite_existing_help(self) -> None:
        def fn():
            return 0
        fn.__tiny_cli_help__ = "Pre-set help"
        app = tc.App(name="t14")
        app.command_from(fn)
        self.assertEqual(fn.__tiny_cli_help__, "Pre-set help")


if __name__ == "__main__":
    unittest.main(verbosity=2)
