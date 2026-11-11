"""Make the color behaviour of this package independent of test file order.

`tiny_cli._NO_COLOR` is computed once, at import time, from
`sys.stdout.isatty()` and the presence of `NO_COLOR` / `TINY_CLI_FORCE_COLOR`.
The test modules force color on with `os.environ.setdefault(...)` in their own
module body — which only works if they are imported before `tiny_cli`.

Under `pytest -q` the collection order is alphabetical, so `test_completion.py`
imports `tiny_cli` first, with no `TINY_CLI_FORCE_COLOR` in the environment.
`_NO_COLOR` consequently latches to `True` and `TestColor::test_style` fails:
`style.red("hi")` returns `"hi"` with no ANSI code.

That made the suite pass file-by-file and fail as a suite. Setting the
environment variable here — at conftest import, which pytest does before it
collects any test module — removes the ordering dependency instead of papering
over it in the assertion.
"""
import os

os.environ["TINY_CLI_FORCE_COLOR"] = "1"
os.environ.pop("TINY_CLI_JSON", None)
