# Changelog

All notable changes to tiny-cli are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.3.3] — 2026-11-25

### Fixed
- **A parameter's type depended on how it was supplied.** `option()` and
  `argument()` declared `type: type = str`, so an omitted `type=` meant `str`
  rather than "infer it". `def top(limit: int = tc.option("--limit", default=10))`
  therefore held `"5"` when the user typed `--limit 5` and `10` when they did
  not — one parameter, two types, chosen by the command line. Every arithmetic
  operation, comparison and JSON envelope downstream behaved differently on the
  two paths. The same root cause made `choices=[1, 2, 3]` reject its own valid
  values: argparse compared the raw string `"2"` against ints and reported
  `invalid choice: '2'`.

  `type` now defaults to `None` and is resolved once, at parser-build time, by
  `_resolve_marker_type()` — explicit `type=` first, then a `str`/`int`/`float`
  annotation, then the type of the declared default, then `str`. A bare `bool`
  annotation still takes the `store_true` branch and never reaches the
  converter.

### Added
- `test_v133_annotation_types.py` — 11 tests. The narrowing half matters as
  much as the fix: `choices` must still reject `--level 9`, `str` annotation
  must beat an `int` default (otherwise "has an annotation" is read as "is
  unannotated"), an explicit `type=str` must beat a `int` annotation, and the
  `bool` flag branch must not regress.

## [1.3.2] — 2026-11-17

### Fixed
- **A flag whose name differed from its parameter name never reached the
  command.** `tc.option("--user")` on `def show(user_id: str = ...)` registered
  an argparse argument whose derived `dest` is `user`, while dispatch looked the
  value up by parameter name, `user_id`. `hasattr(args, "user_id")` was False,
  so the parameter was never bound:

  - flag supplied → silently discarded, command ran on the marker default
  - flag omitted → the raw marker dict was passed as the value

  The second case made the documented JSON contract produce this:

  ```console
  $ myapp show --json
  {"result": {"id": {"_kind": "option", "flags": ["--user"], "default": "1", ...}}}
  ```

  Both are fixed at the source: `add_argument(..., dest=pname)` pins the dest to
  the parameter name for the `store_true` and typed forms alike. Text mode hid
  the defect — the value was formatted into a string nobody compared — so the
  regression test asserts on text mode as well as JSON mode.

### Changed
- A parameter argparse does not populate now has its declared default bound
  explicitly instead of relying on Python's call-time fallback. Marker defaults
  (`option()` / `argument()` descriptors) are skipped, which is what stops the
  descriptor from reaching the command.

### Added
- `test_v131_option_dest.py` — 10 tests. Five fail against 1.3.1; the others
  guard the matching-name, plain-default, required-flag and JSON-purity shapes.
  Every pre-existing test used `times` / `--times`, the one case where
  argparse's derived dest is already correct, which is why 57 tests missed it.
- `test_llms_drift.py` — 35 tests over `llms.txt`: version header, Python
  floor, advertises-every-export, and **executes** the two documented snippets.
  15 fail against the pre-1.3.2 file.

### Fixed (found while writing the docs)
- **An option with no `default=` was not required.** `def add(text: str =
  tc.option("--text"))` registered an optional flag, so omitting it ran the
  command with the descriptor dict as the value. No default now means
  `required=True`, matching the `def f(x)` convention.
- **A parse error wrote `usage: ...` to stdout ahead of the JSON envelope.**
  `| jq` failed to parse while the exit code looked like the app's own. stdout
  is redirected for the parse and the usage line is re-emitted inside the
  envelope's `error` field.
- **A descriptor reaching a command now raises.** Any future path that would
  pass a marker dict is an error, not a silent serialisation.

### Fixed (docs)
- `llms.txt` advertised 1.1.0 on a 1.3.1 package and `Python (3.8+)` against a
  `>=3.9` floor. Its first example called `@cli.option(...)` as a decorator -
  `option` is a default-value marker, so the snippet raised `AttributeError`
  on the first line a new user copies.

### Notes
- No API change. Existing CLIs that used matching names are unaffected.

## [1.3.1] — 2026-11-11

### Fixed
- **The test suite passed file-by-file and failed as a suite.** Under
  `pytest -q`, collection order is alphabetical, so `test_completion.py`
  imported `tiny_cli` *before* `test_tiny_cli.py` got a chance to run
  `os.environ.setdefault("TINY_CLI_FORCE_COLOR", "1")`. `_NO_COLOR` is
  computed once at import, latched to `True`, and
  `TestColor::test_style` failed with `'31' not found in 'hi'` — a colour
  library reporting it had no colour. CI runs one file per command in its
  matrix, which is why a red suite never showed up there.
  Fixed in `conftest.py`, which pytest imports before collecting any test
  module. Same suite, 0 failures, in either file order. No runtime change.

## [1.3.0] — 2026-11-09

### Fixed
- **A command returning a `str` or `dict` crashed in JSON mode.** Every
  non-`None` return was passed through `int()`, so
  `return {"id": 7}` produced
  `{"result": null, "error": "ValueError: invalid literal for int() ...",
  "exit_code": 1}`. Returning data is the documented JSON-mode contract, so
  the documented contract was the code path that failed. Return values are
  now `result` unless they are `int` (still an exit code) or `bool`.
- **`print()` output leaked ahead of the JSON envelope.** Only `echo()` was
  patched out, so any command that printed — or any library it called — put
  lines before the envelope and `--json | jq` failed with a parse error while
  the shell pipeline exit code stayed 0, because `jq` failed rather than the
  CLI. Stdout is now captured for the whole run and replayed into an optional
  `stdout` field of the envelope. `echo()` output is captured there too
  instead of being dropped.
- **`output_mode=` was documented but not accepted as a constructor
  argument.** The class docstring has advertised `output_mode="json"` since
  1.1.0; `App(output_mode="json")` raised `TypeError`. It is now a real
  parameter, validated against `text` / `json` / `silent`.

### Added
- 11 regression tests in `test_v130_json_contract.py`; **10 fail against
  1.2.0** (the 11th is the control — the `--json` flag on an `int`-returning
  command, which already worked and must keep working).

### Notes
- A 1.2.0 caller that returned a non-int and depended on the resulting error
  exit code cannot exist without also ignoring that error, so this is not a
  breaking change in practice. `int` returns are unchanged.

## [1.2.0] — 2026-10-04

### Added
- **`App.from_module(module, *, name=None, help=None, version=None, auto_env=False, env_path=None, prefix="", only_decorated=True)`** — classmethod that auto-discovers commands from a Python module. Accepts either a string dotted-path (`"myapp.commands"`) or an already-imported module object. With `only_decorated=False`, every public function (not starting with `_`) is registered as a subcommand. With `only_decorated=True` (default), only functions that already carry `__tiny_cli_help__` (i.e. were wrapped by `@app.command()`) are registered. Functions whose `__module__` is not the target module (i.e. they were imported from elsewhere) are skipped. The optional `prefix=""` argument namespaces all discovered commands (e.g. `prefix="aws"` turns `def s3_ls():` into `app aws s3-ls`). 11 new tests in `test_v120_from_module.py`.
- **`App.command_from(fn, *, name=None)`** — register a single external function as a command. Equivalent to decorating the function with `@app.command()` but for objects defined outside the `App` class. The function's docstring becomes the help text unless it already has `__tiny_cli_help__` set. 4 new tests.

### Changed
- Bumped `__version__` to `1.2.0`.
- Combined suite now 57/57 (42 existing + 15 new).

### Notes
- `App.from_module` does not import the target module a second time if it's already loaded — it operates on the module object as-is. Pass a string path to trigger `importlib.import_module()`; pass an object to skip the import step.
- The `__module__` check (`getattr(fn, "__module__", None) != mod.__name__`) prevents `from os import path` and similar accidental re-exports from registering `path` as a CLI subcommand. This is the same heuristic that `pytest`'s `collect_imported_tests` filter uses.

## [1.1.0] — 2026-09-15

### Added
- `auto_env=True` — auto-load `.env` (or custom `env_path=`) from cwd before parsing.
- `output_mode="json"` and `output_mode="silent"` — structured and quiet output modes.
- `set_banner(text)` and `set_logo(lines)` — banner above `--help`.
- Theme support for `Table` (`"box"`, `"simple"`, `"markdown"`).
- `Tree` ASCII renderer with Unicode/auto-fallback.
- `--json` global flag and `TINY_CLI_JSON=1` env var for CI integration.
- 42 tests, suite now 42/42.

## [1.0.0] — 2026-08-30

### Added
- Stable API. `App`, `command`, `option`, `argument`, `echo`, `err`, `style`, `Progress`, `Spinner`, `Table`, `Tree`, `status`, `prompt`, `confirm`, `load_env`.

## [0.2.0] — 2026-09-26

### Added
- Shell completion (bash/zsh/fish) via `App(..., shells=(...))` and `install()`.
- Command groups via `App.group(name, **flags)`.
- Async command handlers via `App.async_command()`.
- 19 new tests.

## [0.1.0] — 2026-06-25

### Added
- Initial release: 8 tests covering App, command, option, type coercion, color output.
