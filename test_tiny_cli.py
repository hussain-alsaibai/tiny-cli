"""Tests for tiny-cli. Run with `python test_tiny_cli.py`."""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# Force colors on in the test process (TTY detection fails under pytest/IDE).
os.environ.setdefault("TINY_CLI_FORCE_COLOR", "1")
import tiny_cli as tc


class TestCoerce(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(tc._coerce("42", int), 42)
        self.assertEqual(tc._coerce("3.14", float), 3.14)
        self.assertIs(tc._coerce("true", bool), True)
        self.assertIs(tc._coerce("NO", bool), False)
        self.assertEqual(tc._coerce("hello", str), "hello")
        self.assertEqual(tc._coerce("a,b,c", list), ["a", "b", "c"])


class TestColor(unittest.TestCase):
    def test_style(self):
        # force color on
        out = tc.style.red("hi", color=True)
        self.assertIn("31", out)
        self.assertIn("hi", out)
        # color=False → no codes
        out2 = tc.style.red("hi", color=False)
        self.assertEqual(out2, "hi")


class TestEcho(unittest.TestCase):
    def test_echo(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            tc.echo("hello")
        self.assertIn("hello", buf.getvalue())


class TestAppBasic(unittest.TestCase):
    def test_single_command_no_args(self):
        app = tc.App(name="test1")
        result = {"called": False}

        @app.command()
        def hello():
            """Say hi."""
            result["called"] = True
            return 0

        rc = app.run(argv=["hello"])
        self.assertEqual(rc, 0)
        self.assertTrue(result["called"])

    def test_no_args_shows_help(self):
        app = tc.App(name="test2")

        @app.command()
        def hello():
            """Say hi."""
            return 0

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = app.run(argv=[])
        self.assertEqual(rc, 0)
        self.assertIn("usage", buf.getvalue().lower())


class TestAppPositional(unittest.TestCase):
    def test_positional_arg(self):
        app = tc.App(name="test3")
        out = {"msg": None}

        @app.command()
        def greet(name: str):
            """Greet."""
            out["msg"] = f"hi {name}"
            return 0

        rc = app.run(argv=["greet", "alice"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["msg"], "hi alice")


class TestAppOption(unittest.TestCase):
    def test_option(self):
        app = tc.App(name="test4")
        out = {"msg": None}

        @app.command()
        def greet(
            name: str,
            shout: bool = tc.option("--shout", "-s", default=False, type=bool),
            times: int = tc.option("--times", "-n", default=1, type=int),
        ):
            """Greet."""
            out["msg"] = ("HI " + name) * times if shout else ("hi " + name) * times
            return 0

        rc = app.run(argv=["greet", "alice", "--shout", "--times", "2"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["msg"], "HI aliceHI alice")

    def test_default_value(self):
        app = tc.App(name="test5")
        out = {"msg": None}

        @app.command()
        def greet(name: str, times: int = tc.option("--times", default=1, type=int)):
            """Greet."""
            out["msg"] = ("hi " + name) * times
            return 0

        rc = app.run(argv=["greet", "bob"])
        self.assertEqual(rc, 0)
        self.assertEqual(out["msg"], "hi bob")


class TestErrorHandling(unittest.TestCase):
    def test_keyboard_interrupt(self):
        app = tc.App(name="test6")

        @app.command()
        def boom():
            raise KeyboardInterrupt()

        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            rc = app.run(argv=["boom"])
        self.assertEqual(rc, 130)

    def test_generic_exception(self):
        app = tc.App(name="test7")

        @app.command()
        def boom():
            raise ValueError("nope")

        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            rc = app.run(argv=["boom"])
        self.assertEqual(rc, 1)
        self.assertIn("nope", buf_err.getvalue())


class TestConfirm(unittest.TestCase):
    def test_yes(self):
        sys.stdin = io.StringIO("y\n")
        sys.stdout = io.StringIO()
        self.assertTrue(tc.confirm("ok?", default=False))
        sys.stdout = sys.__stdout__

    def test_no(self):
        sys.stdin = io.StringIO("n\n")
        sys.stdout = io.StringIO()
        self.assertFalse(tc.confirm("ok?", default=True))
        sys.stdout = sys.__stdout__

    def test_default(self):
        # First call: default=True, empty input → True
        sys.stdin = io.StringIO("\n")
        sys.stdout = io.StringIO()
        r1 = tc.confirm("ok?", default=True)
        # Second call: default=False, empty input → False
        sys.stdin = io.StringIO("\n")
        r2 = tc.confirm("ok?", default=False)
        sys.stdout = sys.__stdout__
        self.assertTrue(r1)
        self.assertFalse(r2)


if __name__ == "__main__":
    unittest.main()
