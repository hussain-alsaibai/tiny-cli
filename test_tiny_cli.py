"""Tests for tiny-cli. Run with `python test_tiny_cli.py`."""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
# Force colors on in the test process (TTY detection fails under pytest/IDE).
os.environ.setdefault("TINY_CLI_FORCE_COLOR", "1")
# Wipe any JSON mode inherited from the environment.
os.environ.pop("TINY_CLI_JSON", None)
import tiny_cli as tc  # noqa: E402


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
        self.assertEqual(rc, tc.ABORT)
        self.assertEqual(rc, 130)

    def test_generic_exception(self):
        app = tc.App(name="test7")

        @app.command()
        def boom():
            raise ValueError("nope")

        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            rc = app.run(argv=["boom"])
        self.assertEqual(rc, tc.ERROR)
        self.assertEqual(rc, 1)
        self.assertIn("nope", buf_err.getvalue())

    def test_argument_error(self):
        app = tc.App(name="test7b")

        @app.command()
        def add(a: float, b: float):
            """Add."""
            return 0

        buf_err = io.StringIO()
        with redirect_stderr(buf_err):
            rc = app.run(argv=["add", "not_a_number", "2"])
        self.assertEqual(rc, tc.USAGE)


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


# ---------------------------------------------------------------------------
# v1.1.0 — Table themes / filter / sort
# ---------------------------------------------------------------------------


class TestTableThemes(unittest.TestCase):
    def test_box_theme_default(self):
        t = tc.Table(["Name", "Size"])
        t.add_row("foo", "1 KB")
        out = str(t)
        self.assertIn("┌", out)
        self.assertIn("│", out)
        self.assertIn("└", out)
        self.assertIn("foo", out)
        self.assertIn("1 KB", out)

    def test_simple_theme(self):
        t = tc.Table(["Name", "Size"], theme="simple")
        t.add_row("foo", "1 KB")
        out = str(t)
        self.assertIn("---", out)
        self.assertIn("foo", out)
        self.assertNotIn("┌", out)

    def test_markdown_theme(self):
        t = tc.Table(["Name", "Size"], theme="markdown")
        t.add_row("foo", "1 KB")
        t.add_row("bar", "2 KB")
        out = str(t)
        # markdown header row
        self.assertIn("| Name", out)
        # separator row uses at least 3 dashes per column
        self.assertIn("---", out)
        self.assertIn("| foo", out)
        self.assertIn("| bar", out)


class TestTableFilterSort(unittest.TestCase):
    def setUp(self):
        self.t = tc.Table(["Name", "Size", "Modified"])
        self.t.add_row("a", "10", "2026-01-01")
        self.t.add_row("b", "30", "2026-01-03")
        self.t.add_row("c", "20", "2026-01-02")

    def test_filter_cols(self):
        self.t.filter_cols("Name", "Size")
        self.assertEqual(self.t.headers, ["Name", "Size"])
        self.assertEqual(self.t.rows[0], ["a", "10"])
        self.assertEqual(len(self.t.rows), 3)

    def test_sort_by(self):
        self.t.sort_by("Size")
        self.assertEqual(self.t.rows[0][0], "a")
        self.assertEqual(self.t.rows[1][0], "c")
        self.assertEqual(self.t.rows[2][0], "b")

    def test_sort_by_reverse(self):
        self.t.sort_by("Size", reverse=True)
        self.assertEqual(self.t.rows[0][0], "b")
        self.assertEqual(self.t.rows[2][0], "a")


# ---------------------------------------------------------------------------
# v1.1.0 — Tree renderer
# ---------------------------------------------------------------------------


class TestTree(unittest.TestCase):
    def test_simple_tree(self):
        t = tc.Tree(root_label="root/")
        t.add("README.md", "file")
        t.add("src/", "dir")
        t.add("src/main.py", "file")
        out = str(t)
        self.assertIn("root/", out)
        self.assertIn("README.md", out)
        self.assertIn("src/", out)
        self.assertIn("main.py", out)

    def test_tree_ascii(self):
        t = tc.Tree(root_label="")
        t.add("dir/", "dir")
        t.add("dir/a.txt", "file")
        t.set_ascii(True)
        out = str(t)
        # ASCII mode uses "|--" or "`--" for branches
        self.assertTrue("|--" in out or "`--" in out, f"expected ASCII branch glyph in {out!r}")
        self.assertIn("a.txt", out)

    def test_tree_nested(self):
        t = tc.Tree()
        t.add("a/b/c.py", "file")
        t.add("a/b/d.py", "file")
        t.add("a/e.py", "file")
        out = str(t)
        self.assertIn("a", out)
        self.assertIn("b", out)
        self.assertIn("c.py", out)
        self.assertIn("e.py", out)

    def test_tree_returns_self(self):
        t = tc.Tree()
        self.assertIs(t.add("x.py", "file"), t)
        self.assertIs(t.set_ascii(True), t)


# ---------------------------------------------------------------------------
# v1.1.0 — JSON output mode
# ---------------------------------------------------------------------------


class TestJsonMode(unittest.TestCase):
    def test_json_via_flag(self):
        app = tc.App(name="j1")

        @app.command()
        def hello():
            return 0

        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = app.run(argv=["hello", "--json"])
        self.assertEqual(rc, 0)
        # JSON envelope should be on stdout
        data = json.loads(buf_out.getvalue().strip())
        self.assertEqual(data["command"], "hello")
        self.assertEqual(data["exit_code"], 0)
        self.assertIsNone(data["error"])

    def test_json_via_env(self):
        old = os.environ.get("TINY_CLI_JSON")
        os.environ["TINY_CLI_JSON"] = "1"
        try:
            app = tc.App(name="j2")
            # Direct check: the App object should reflect JSON mode
            self.assertEqual(app.output_mode, "json")
        finally:
            if old is None:
                os.environ.pop("TINY_CLI_JSON", None)
            else:
                os.environ["TINY_CLI_JSON"] = old

    def test_json_error_envelope(self):
        app = tc.App(name="j3")

        @app.command()
        def boom():
            raise ValueError("kaboom")

        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = app.run(argv=["boom", "--json"])
        self.assertEqual(rc, tc.ERROR)
        # JSON envelope may be on stdout OR stderr depending on env vs flag.
        combined = buf_out.getvalue() + buf_err.getvalue()
        self.assertIn("kaboom", combined)

    def test_json_abort_envelope(self):
        app = tc.App(name="j4")

        @app.command()
        def boom():
            raise KeyboardInterrupt()

        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = app.run(argv=["boom", "--json"])
        self.assertEqual(rc, tc.ABORT)
        combined = buf_out.getvalue() + buf_err.getvalue()
        self.assertIn("aborted", combined)

    def test_json_help_envelope(self):
        """When --help is passed with --json, emit a JSON help envelope."""
        app = tc.App(name="j5")

        @app.command()
        def hello():
            return 0

        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = app.run(argv=["--help", "--json"])
        self.assertEqual(rc, tc.OK)
        # argparse prints human-readable help first, then our JSON envelope
        # is appended. Take the last non-empty line as the JSON payload.
        lines = [ln for ln in buf_out.getvalue().splitlines() if ln.strip().startswith("{")]
        self.assertTrue(lines, "expected a JSON envelope line in stdout")
        data = json.loads(lines[-1])
        self.assertIn("help", data["result"])
        self.assertEqual(data["exit_code"], tc.OK)


# ---------------------------------------------------------------------------
# v1.1.0 — output_mode = silent
# ---------------------------------------------------------------------------


class TestSilentMode(unittest.TestCase):
    def test_silent_app_attribute(self):
        app = tc.App(name="s1")
        app.output_mode = "silent"
        self.assertEqual(app.output_mode, "silent")


# ---------------------------------------------------------------------------
# v1.1.0 — auto-env loading
# ---------------------------------------------------------------------------


class TestAutoEnv(unittest.TestCase):
    def test_parse_env_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text(
                "# comment\n"
                "FOO=bar\n"
                "export BAZ=qux\n"
                "QUOTED=\"hello world\"\n"
                "SINGLE='no expand'\n"
                "\n"
                "EMPTY=\n"
            )
            result = tc._parse_env_file(p)
            self.assertEqual(result["FOO"], "bar")
            self.assertEqual(result["BAZ"], "qux")
            self.assertEqual(result["QUOTED"], "hello world")
            self.assertEqual(result["SINGLE"], "no expand")
            self.assertEqual(result["EMPTY"], "")

    def test_load_env_sets_environ(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("TINYCLI_TEST_X=hello\nTINYCLI_TEST_Y=42\n")
            # Make sure they aren't already set
            os.environ.pop("TINYCLI_TEST_X", None)
            os.environ.pop("TINYCLI_TEST_Y", None)
            tc.load_env(p)
            self.assertEqual(os.environ.get("TINYCLI_TEST_X"), "hello")
            self.assertEqual(os.environ.get("TINYCLI_TEST_Y"), "42")

    def test_load_env_no_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("TINYCLI_TEST_KEEP=fromfile\n")
            os.environ["TINYCLI_TEST_KEEP"] = "preset"
            tc.load_env(p, override=False)
            self.assertEqual(os.environ["TINYCLI_TEST_KEEP"], "preset")

    def test_load_env_with_override(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / ".env"
            p.write_text("TINYCLI_TEST_OVR=fromfile\n")
            os.environ["TINYCLI_TEST_OVR"] = "preset"
            tc.load_env(p, override=True)
            self.assertEqual(os.environ["TINYCLI_TEST_OVR"], "fromfile")

    def test_app_auto_env(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            try:
                os.chdir(d)
                p = Path(d) / ".env"
                p.write_text("TINYCLI_AUTO=works\n")
                os.environ.pop("TINYCLI_AUTO", None)
                app = tc.App(name="envtest", auto_env=True)
                self.assertEqual(os.environ.get("TINYCLI_AUTO"), "works")
                # Also verify a custom path works.
            finally:
                os.chdir(cwd)
                os.environ.pop("TINYCLI_AUTO", None)


# ---------------------------------------------------------------------------
# v1.1.0 — banner / logo
# ---------------------------------------------------------------------------


class TestBanner(unittest.TestCase):
    def test_set_banner_returns_self(self):
        app = tc.App(name="b1")
        self.assertIs(app.set_banner("hello"), app)

    def test_set_logo_returns_self(self):
        app = tc.App(name="b2")
        self.assertIs(app.set_logo(["line1", "line2"]), app)

    def test_banner_not_printed_by_default(self):
        app = tc.App(name="b3")
        app.set_banner("=== my banner ===")

        @app.command()
        def hi():
            return 0

        buf = io.StringIO()
        with redirect_stdout(buf):
            app.run(argv=["hi"])
        self.assertNotIn("=== my banner ===", buf.getvalue())

    def test_banner_with_env(self):
        app = tc.App(name="b4")
        app.set_banner("=== my banner ===")
        old = os.environ.get("TINY_CLI_SHOW_BANNER")
        os.environ["TINY_CLI_SHOW_BANNER"] = "1"
        try:
            buf_out, buf_err = io.StringIO(), io.StringIO()
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                app.run(argv=[])
            combined = buf_out.getvalue() + buf_err.getvalue()
            self.assertIn("=== my banner ===", combined)
        finally:
            if old is None:
                os.environ.pop("TINY_CLI_SHOW_BANNER", None)
            else:
                os.environ["TINY_CLI_SHOW_BANNER"] = old

    def test_logo_and_banner(self):
        app = tc.App(name="b5")
        app.set_logo(["AAA", "BBB"])
        app.set_banner("== banner ==")
        old = os.environ.get("TINY_CLI_SHOW_BANNER")
        os.environ["TINY_CLI_SHOW_BANNER"] = "1"
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                app.run(argv=[])
            self.assertIn("AAA", buf.getvalue())
            self.assertIn("BBB", buf.getvalue())
            self.assertIn("== banner ==", buf.getvalue())
        finally:
            if old is None:
                os.environ.pop("TINY_CLI_SHOW_BANNER", None)
            else:
                os.environ["TINY_CLI_SHOW_BANNER"] = old


# ---------------------------------------------------------------------------
# v1.1.0 — exit-code constants
# ---------------------------------------------------------------------------


class TestExitCodes(unittest.TestCase):
    def test_constants(self):
        self.assertEqual(tc.OK, 0)
        self.assertEqual(tc.ERROR, 1)
        self.assertEqual(tc.USAGE, 2)
        self.assertEqual(tc.INTERNAL, 3)
        self.assertEqual(tc.ABORT, 130)

    def test_in_all(self):
        for name in ("OK", "ERROR", "USAGE", "INTERNAL", "ABORT"):
            self.assertIn(name, tc.__all__)


if __name__ == "__main__":
    unittest.main()
