"""Regression tests for option() with a flag name that differs from the param.

`tc.option("--user", ...)` is a *default-value marker*. The parameter is
`user_id`; the flag is `--user`. argparse derives `dest` from the flag
(`user`), while the dispatcher looked the value up by parameter name
(`user_id`). The two differ, `hasattr(args, "user_id")` is False, and the
parameter was never bound:

  - supplied flag: silently discarded, command ran on the marker default
  - omitted flag:  the raw marker dict was passed to the command, so
    `{"id": user_id}` serialised as
    `{"id": {"_kind": "option", "flags": ["--user"], ...}}`

in JSON mode. Text mode hid it: the command raised or formatted the dict
into a string nobody read.

Every pre-existing test used a matching name (`times` / `--times`), which is
the single case where argparse's derived dest is already correct. That is why
a suite of 57 tests never caught it.

Each test below fails on the unfixed module.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout

import pytest

import tiny_cli as tc


def _run_json(app_builder, argv):
    """Run an app in JSON mode and return the parsed envelope."""
    app = app_builder()
    buf = io.StringIO()
    with redirect_stdout(buf):
        app.output_mode = "json"
        rc = app.run(argv=argv)
    text = buf.getvalue().strip()
    assert text, f"no envelope written; rc={rc}"
    return json.loads(text), rc


def test_mismatched_option_name_receives_supplied_value():
    seen = {}

    def build():
        app = tc.App("t")

        @app.command()
        def show(user_id: str = tc.option("--user", default="1")):
            seen["user_id"] = user_id
            return {"id": user_id}

        return app

    env, rc = _run_json(build, ["show", "--user", "9"])
    assert rc == 0
    assert seen["user_id"] == "9", f"command saw {seen['user_id']!r}, expected '9'"
    assert env["result"] == {"id": "9"}


def test_mismatched_option_name_uses_declared_default():
    seen = {}

    def build():
        app = tc.App("t")

        @app.command()
        def show(user_id: str = tc.option("--user", default="7")):
            seen["user_id"] = user_id
            return {"id": user_id}

        return app

    env, rc = _run_json(build, ["show"])
    assert rc == 0
    assert seen["user_id"] == "7", f"command saw {seen['user_id']!r}, expected '7'"
    assert isinstance(env["result"]["id"], str), (
        "the marker dict leaked into the result: " + json.dumps(env["result"])
    )


def test_marker_dict_never_reaches_the_command():
    """The exact defect shape: a dict result containing the marker."""
    def build():
        app = tc.App("t")

        @app.command()
        def show(user_id: str = tc.option("--user", default="1")):
            return {"id": user_id}

        return app

    env, _ = _run_json(build, ["show"])
    assert "_kind" not in json.dumps(env["result"])


def test_bool_flag_with_mismatched_name():
    seen = {}

    def build():
        app = tc.App("t")

        @app.command()
        def run(verbose_flag: bool = tc.option("--verbose", "-v", default=False, type=bool)):
            seen["v"] = verbose_flag
            return {"verbose": verbose_flag}

        return app

    env, _ = _run_json(build, ["run", "-v"])
    assert env["result"] == {"verbose": True}
    assert seen["v"] is True


def test_matching_name_still_works():
    """The previously-working shape must not regress."""
    seen = {}

    def build():
        app = tc.App("t")

        @app.command()
        def greet(name: str, times: int = tc.option("--times", default=2, type=int)):
            seen["times"] = times
            return {"n": times}

        return app

    env, _ = _run_json(build, ["greet", "bob", "--times", "3"])
    assert env["result"] == {"n": 3}
    assert seen["times"] == 3


def test_plain_default_is_bound_not_dropped():
    """A non-marker parameter argparse does not populate keeps its default.

    Before the fix this worked only because Python's own default kicked in
    on the call. Binding it explicitly keeps text and JSON mode identical
    when a parameter is filtered for another reason.
    """
    def build():
        app = tc.App("t")

        @app.command()
        def ping(times: int = 4):
            return {"times": times}

        return app

    env, _ = _run_json(build, ["ping"])
    assert env["result"] == {"times": 4}
    assert env["args"] == {"times": 4}


def test_text_mode_receives_same_value_as_json_mode():
    """The bug was invisible in text mode; both modes must agree now."""
    seen = []

    def build():
        app = tc.App("t")

        @app.command()
        def show(user_id: str = tc.option("--user", default="1")):
            seen.append(user_id)
            tc.echo(f"id={user_id}")
            return 0

        return app

    buf = io.StringIO()
    with redirect_stdout(buf):
        build().run(argv=["show", "--user", "42"])
    assert "id=42" in buf.getvalue(), buf.getvalue()
    assert seen == ["42"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))


# --- second defect found while writing the docs: no-default options were
# --- optional, and a parse error corrupted the JSON envelope.

def test_option_without_default_is_required():
    """`def f(x=tc.option("--x"))` with no `default=` must be a required flag."""
    def build():
        app = tc.App("t")

        @app.command()
        def add(text: str = tc.option("--text")):
            return {"text": text}

        return app

    env, rc = _run_json(build, ["add"])
    assert rc == 2, f"omitting a required flag must fail with usage, got rc={rc}"
    assert env["result"] is None
    assert "parse error" in (env["error"] or "")

    env, rc = _run_json(build, ["add", "--text", "hi"])
    assert rc == 0
    assert env["result"] == {"text": "hi"}


def test_parse_error_keeps_stdout_json_only():
    """argparse used to print `usage:` to stdout ahead of the envelope."""
    def build():
        app = tc.App("t")

        @app.command()
        def add(text: str = tc.option("--text")):
            return {"text": text}

        return app

    env, _ = _run_json(build, ["add"])
    # _run_json already json.loads() the captured stdout; reaching here means
    # stdout was a single parseable document with nothing before it.
    assert env["exit_code"] == 2
    assert "usage:" in env["error"], "the usage line was dropped, not relocated"


def test_descriptor_never_reaches_command_under_any_path():
    """Belt and braces: a marker in kwargs raises instead of serialising."""
    def build():
        app = tc.App("t")

        @app.command()
        def show(user_id: str = tc.option("--user", default="1")):
            return {"id": user_id}

        return app

    for argv in (["show"], ["show", "--user", "3"]):
        env, rc = _run_json(build, argv)
        assert "_kind" not in json.dumps(env), argv
        assert rc == 0, argv
