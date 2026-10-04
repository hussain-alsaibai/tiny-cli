# Changelog

All notable changes to tiny-cli are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
