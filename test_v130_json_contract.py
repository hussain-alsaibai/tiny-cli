"""v1.3.0 — the JSON envelope is a machine contract.

Three defects, all visible only from the *consumer's* side (a pipe into
`jq`), none visible from the producer's side:

1. A command returning a str/dict raised `ValueError: invalid literal for
   int()`, because every non-None return was fed through int(). Returning
   data is the documented contract for JSON mode, so the documented contract
   was the thing that crashed.
2. A command that printed to stdout leaked those lines ahead of the
   envelope. `--json | jq` got "parse error: Invalid numeric literal" and the
   exit code still said 0 in the shell pipeline, because jq failed, not us.
3. `output_mode="json"` was documented in the class docstring since 1.1.0 but
   absent from __init__, so it raised TypeError.

Each test below fails against 1.2.0.
"""

import io
import json
import unittest
from contextlib import redirect_stdout

import tiny_cli as tc


class TestReturnValueIsData(unittest.TestCase):
    def test_string_return_is_the_result(self):
        app = tc.App(name="j1", output_mode="json")

        @app.command()
        def hello():
            return "the-result"

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = app.run(argv=["hello"])
        self.assertEqual(rc, tc.OK, "a data return must not be an error")
        data = json.loads(buf.getvalue().strip())
        self.assertEqual(data["result"], "the-result")
        self.assertIsNone(data["error"])

    def test_dict_return_is_the_result(self):
        app = tc.App(name="j2", output_mode="json")

        @app.command()
        def payload():
            return {"id": 7, "tags": ["a", "b"]}

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = app.run(argv=["payload"])
        self.assertEqual(rc, tc.OK)
        data = json.loads(buf.getvalue().strip())
        self.assertEqual(data["result"], {"id": 7, "tags": ["a", "b"]})

    def test_int_return_is_still_an_exit_code(self):
        """Exit codes must keep working; data returns changed, ints did not."""
        app = tc.App(name="j3", output_mode="json")

        @app.command()
        def fail():
            return 4

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = app.run(argv=["fail"])
        self.assertEqual(rc, 4)
        self.assertEqual(json.loads(buf.getvalue().strip())["exit_code"], 4)

    def test_none_return_is_still_ok(self):
        app = tc.App(name="j4", output_mode="json")

        @app.command()
        def quiet():
            return None

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = app.run(argv=["quiet"])
        self.assertEqual(rc, tc.OK)


class TestEnvelopeOwnsStdout(unittest.TestCase):
    def test_print_does_not_leak_into_stdout(self):
        app = tc.App(name="j5", output_mode="json")

        @app.command()
        def noisy():
            print("chatter on stdout")
            print("more chatter")
            return {"done": True}

        buf = io.StringIO()
        with redirect_stdout(buf):
            app.run(argv=["noisy"])

        raw = buf.getvalue()
        # The whole of stdout must be exactly one parseable JSON document.
        data = json.loads(raw)
        self.assertEqual(raw.strip().count("\n"), 0, f"envelope was not a single line: {raw!r}")
        self.assertEqual(data["result"], {"done": True})
        self.assertIn("chatter on stdout", data["stdout"])

    def test_leaked_stdout_on_error_is_captured_too(self):
        app = tc.App(name="j6", output_mode="json")

        @app.command()
        def boom():
            print("before the crash")
            raise ValueError("kaboom")

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = app.run(argv=["boom"])

        self.assertEqual(rc, tc.ERROR)
        data = json.loads(buf.getvalue())
        self.assertIn("kaboom", data["error"])
        self.assertIn("before the crash", data["stdout"])

    def test_echo_is_captured_not_dropped(self):
        """echo() was patched to a no-op in 1.2.0; now it is captured."""
        app = tc.App(name="j7", output_mode="json")

        @app.command()
        def chatty():
            tc.echo("styled line")
            return 0

        buf = io.StringIO()
        with redirect_stdout(buf):
            app.run(argv=["chatty"])
        data = json.loads(buf.getvalue())
        self.assertIn("styled line", data["stdout"])


class TestOutputModeParameter(unittest.TestCase):
    def test_constructor_accepts_output_mode(self):
        app = tc.App(name="j8", output_mode="json")
        self.assertEqual(app.output_mode, "json")

    def test_constructor_accepts_silent(self):
        app = tc.App(name="j9", output_mode="silent")
        self.assertEqual(app.output_mode, "silent")

    def test_unknown_output_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            tc.App(name="j10", output_mode="yaml")

    def test_flag_overrides_text_default(self):
        app = tc.App(name="j11")
        self.assertEqual(app.output_mode, "text")

        @app.command()
        def x():
            return 0

        buf = io.StringIO()
        with redirect_stdout(buf):
            app.run(argv=["x", "--json"])
        self.assertIsNotNone(json.loads(buf.getvalue().strip())["command"])


if __name__ == "__main__":
    unittest.main()
