"""Regression tests for 1.3.3: a parameter's type must not depend on how it was supplied.

The defect: ``@option``/``@argument`` defaulted ``type`` to ``str``. So

    def top(limit: int = tc.option("--limit", default=10)): ...

produced ``limit == "5"`` when the user typed ``--limit 5`` and ``limit == 10``
when they did not. One parameter, two types, chosen by the user's command line.
Everything that consumed the value -- arithmetic, comparisons, a JSON envelope
-- behaved differently on the two paths, and the existing tests never caught it
because every one of them wrote ``type=int`` explicitly: the single spelling
that could not fail.

The same root cause made ``choices`` reject its own valid values. With the
converter pinned to ``str``, argparse compared the raw string ``"2"`` against
``[1, 2, 3]`` and reported ``invalid choice: '2'``.
"""

import contextlib
import io
import json

import pytest

import tiny_cli as tc


def run_json(build, argv):
    """Run a freshly built app in JSON mode; return (envelope, exit code)."""
    app = build()
    app.output_mode = "json"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = app.run(argv=argv)
    text = buf.getvalue().strip()
    assert text, f"no envelope written; rc={rc}"
    return json.loads(text), rc


def run_stderr(build, argv):
    """Run in text mode; return (exit code, stderr text)."""
    app = build()
    err = io.StringIO()
    code = None
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
        try:
            code = app.run(argv=argv)
        except SystemExit as exc:
            code = exc.code
    return code, err.getvalue()


# --- the reported defect -------------------------------------------------


def test_annotated_int_option_is_int_when_supplied():
    def build():
        app = tc.App("t")

        @app.command()
        def top(limit: int = tc.option("--limit", default=10)):
            """Limit."""
            return {"limit": limit, "type": type(limit).__name__}

        return app

    env, rc = run_json(build, ["top", "--limit", "5"])
    assert rc == 0
    assert env["result"] == {"limit": 5, "type": "int"}


def test_annotated_int_option_matches_its_default_type():
    """The two paths must agree -- that IS the invariant being fixed."""

    def build():
        app = tc.App("t")

        @app.command()
        def top(limit: int = tc.option("--limit", default=10)):
            """Limit."""
            return {"type": type(limit).__name__}

        return app

    supplied, _ = run_json(build, ["top", "--limit", "5"])
    omitted, _ = run_json(build, ["top"])
    assert supplied["result"] == omitted["result"] == {"type": "int"}


def test_int_choices_accept_their_own_values():
    def build():
        app = tc.App("t")

        @app.command()
        def pick(level: int = tc.option("--level", default=1, choices=[1, 2, 3])):
            """Pick."""
            return {"level": level}

        return app

    env, rc = run_json(build, ["pick", "--level", "2"])
    assert rc == 0
    assert env["result"] == {"level": 2}


def test_int_choices_still_reject_an_out_of_range_value():
    """The narrowing half: the fix must not turn ``choices`` into a no-op."""

    def build():
        app = tc.App("t")

        @app.command()
        def pick(level: int = tc.option("--level", default=1, choices=[1, 2, 3])):
            """Pick."""
            return {"level": level}

        return app

    code, err = run_stderr(build, ["pick", "--level", "9"])
    assert code == 2
    assert "invalid choice" in err


# --- the same rule on the other declaration forms ------------------------


def test_annotated_positional_argument_is_int():
    def build():
        app = tc.App("t")

        @app.command()
        def count_n(n: int):
            """Count."""
            return {"n": n, "type": type(n).__name__}

        return app

    env, _ = run_json(build, ["count-n", "8"])
    assert env["result"] == {"n": 8, "type": "int"}


def test_argument_marker_uses_the_annotation():
    def build():
        app = tc.App("t")

        @app.command()
        def arglist(count: int = tc.argument("count", default=3)):
            """Count."""
            return {"count": count, "type": type(count).__name__}

        return app

    env, _ = run_json(build, ["arglist", "8"])
    assert env["result"] == {"count": 8, "type": "int"}


def test_unannotated_option_infers_type_from_its_default():
    def build():
        app = tc.App("t")

        @app.command()
        def inferred(x=tc.option("--x", default=2.5)):
            """Inferred."""
            return {"x": x, "type": type(x).__name__}

        return app

    env, _ = run_json(build, ["inferred", "--x", "1.5"])
    assert env["result"] == {"x": 1.5, "type": "float"}


# --- explicit intent still wins -----------------------------------------


def test_explicit_type_overrides_the_annotation():
    def build():
        app = tc.App("t")

        @app.command()
        def raw(n: int = tc.option("--n", type=str)):
            """Raw."""
            return {"n": n, "type": type(n).__name__}

        return app

    env, _ = run_json(build, ["raw", "--n", "7"])
    assert env["result"] == {"n": "7", "type": "str"}


def test_annotated_str_stays_str():
    """An annotation of ``str`` must not be read as "unannotated"."""

    def build():
        app = tc.App("t")

        @app.command()
        def name_tag(tag: str = tc.option("--tag", default=0)):
            """Str annotation beats an int default."""
            return {"tag": tag, "type": type(tag).__name__}

        return app

    env, _ = run_json(build, ["name-tag", "--tag", "7"])
    assert env["result"] == {"tag": "7", "type": "str"}


def test_bool_option_is_still_a_store_true_flag():
    """The bool branch never goes through the converter; it must not regress."""

    def build():
        app = tc.App("t")

        @app.command()
        def go(verbose: bool = tc.option("--verbose", default=False)):
            """Go."""
            return {"verbose": verbose}

        return app

    on, _ = run_json(build, ["go", "--verbose"])
    off, _ = run_json(build, ["go"])
    assert on["result"] == {"verbose": True}
    assert off["result"] == {"verbose": False}


def test_bool_flag_default_is_honoured():
    """A ``--flag`` with default=True stays True when omitted (existing 1.3.2 rule)."""

    def build():
        app = tc.App("t")

        @app.command()
        def go(quiet: bool = tc.option("--quiet", default=True)):
            """Go."""
            return {"quiet": quiet}

        return app

    env, _ = run_json(build, ["go"])
    assert env["result"] == {"quiet": True}
