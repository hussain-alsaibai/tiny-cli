# tiny-cli

> Zero-dependency CLI builder for Python. Decorators, color, prompts, JSON output, tree rendering, auto-env — argparse without the bloat, built for AI agents and scripts.

```bash
pip install tiny-cli   # coming soon
```

## Why?

- **`argparse`** — verbose, no colors, no prompts, no JSON
- **`click`** — 1 dep (`markupsafe`), heavy
- **`typer`** — 6 deps, requires pydantic + click

**tiny-cli** is a single file, zero deps, gives you the 90% case: commands, options, color, prompts, JSON mode, tree rendering, `.env` loading, themed tables.

## What's new in v1.1.0

| Feature | Description |
|---------|-------------|
| **JSON output mode** | `--json` / `TINY_CLI_JSON=1` — emits a single `{command, args, result, error, exit_code}` envelope. Perfect for cron, CI, and AI agents. |
| **`Tree` renderer** | ASCII/Unicode tree visualizer for directory/file hierarchies. Auto-detects TTY, falls back to `|--` style. |
| **Agent output modes** | `App.output_mode = "text" \| "json" \| "silent"`. `silent` routes all status/errors to stderr, only `echo()` to stdout — agent-safe. |
| **Auto-env loading** | `App(auto_env=True)` parses `.env` from cwd (stdlib only — no `python-dotenv` dep). Quoted values, comments, `export` prefix all supported. |
| **Themed `Table`** | `theme="box"` (Unicode), `"simple"` (ASCII), `"markdown"` (GitHub). Plus `filter_cols(*names)` and `sort_by(col, reverse=...)`. |
| **Banner / logo** | `set_banner(text)` + `set_logo(lines)`. Shown on `--help` and startup with `TINY_CLI_SHOW_BANNER=1`. |
| **Exit code constants** | `OK=0`, `ERROR=1`, `USAGE=2`, `INTERNAL=3`, `ABORT=130`. |

## Usage

```python
import tiny_cli as tc
import sys

app = tc.App(name="mytool", help="My CLI tool")

@app.command(help="Greet someone.")
def greet(
    name: str,
    times: int = tc.option("--times", "-n", default=1, type=int, help="how many times"),
    shout: bool = tc.option("--shout", "-s", default=False, type=bool, help="uppercase"),
):
    msg = f"Hello, {name}!" * times
    if shout:
        msg = msg.upper()
    tc.echo(tc.style.green(msg))

@app.command(help="Add two numbers.")
def add(a: float, b: float):
    tc.echo(tc.style.cyan(f"{a} + {b} = {a + b}"))

@app.command(help="Destructive operation with confirmation.")
def rm(path: str, force: bool = tc.option("--force", "-f", default=False, type=bool)):
    if not force and not tc.confirm(f"Really delete {path}?"):
        tc.echo("aborted")
        return
    tc.echo(f"removing {path}")

sys.exit(app.run())
```

```bash
$ mytool greet alice --shout --times 3
HELLO, ALICE!HELLO, ALICE!HELLO, ALICE!

$ mytool add 2 3
2.0 + 3.0 = 5.0

$ mytool rm /etc/passwd
? Really delete /etc/passwd? [y/N]:
```

## JSON output mode (agents, scripts, CI)

Set `TINY_CLI_JSON=1` or pass `--json` to get a single JSON envelope on stdout. Errors still go to stderr. The exit code is preserved.

```bash
$ TINY_CLI_JSON=1 mytool greet alice --shout --times 2
{"command": "greet", "args": {"name": "alice", "times": 2, "shout": true}, "result": null, "error": null, "exit_code": 0}

$ TINY_CLI_JSON=1 mytool add 2 3
{"command": "add", "args": {"a": 2.0, "b": 3.0}, "result": null, "error": null, "exit_code": 0}

$ TINY_CLI_JSON=1 mytool greet
{"command": "greet", "args": null, "result": null, "error": "parse error (exit 2)", "exit_code": 2}
```

Pipe it into `jq`:

```bash
$ TINY_CLI_JSON=1 mytool greet alice | jq -r '.exit_code'
0
```

## Tree renderer

```python
t = tc.Tree(root_label="myproject/")
t.add("src/", "dir")
t.add("src/main.py", "file")
t.add("src/utils.py", "file")
t.add("tests/", "dir")
t.add("tests/test_main.py", "file")
t.add("README.md", "file")
print(t)
```

Output (TTY — Unicode):

```
myproject/
src/
├── main.py
└── utils.py
tests/
└── test_main.py
README.md
```

Force ASCII for log files:

```python
t.set_ascii(True)
```

## Auto-env loading

```python
app = tc.App(name="mytool", auto_env=True)
# Loads ./.env into os.environ before any command runs.
```

Or with a custom path / override:

```python
app = tc.App(name="mytool", auto_env="/etc/myapp/prod.env")
# Or pass True plus env_path:
app = tc.App(name="mytool", auto_env=True, env_path="config/.env")
```

The loader understands:

```bash
# this is a comment
KEY=value
export OTHER=thing
QUOTED="hello world"
SINGLE='no expand'
```

It is stdlib-only (no `python-dotenv`), and respects existing env vars unless `override=True`.

## Themed tables

```python
t = tc.Table(["Name", "Size", "Modified"], theme="markdown")
t.add_row("tiny-cli", "8 KB", "2026-08-30")
t.add_row("tiny-log", "12 KB", "2026-08-28")
t.add_row("tiny-pool", "20 KB", "2026-08-29")
t.sort_by("Size", reverse=True)
t.filter_cols("Name", "Size")
print(t)
```

Output (theme=`markdown`):

```
| Name      | Size  |
| --------- | ----- |
| tiny-pool | 20 KB |
| tiny-log  | 12 KB |
| tiny-cli  | 8 KB  |
```

Themes:

- `"box"` — Unicode box-drawing (`┌ ┐ │ ─`)
- `"simple"` — ASCII (`-` separators only)
- `"markdown"` — GitHub-flavored pipe table

## Banner and logo

```python
app = tc.App(name="mytool")
app.set_logo([
    "  __ _  ___   _ _ ",
    " / _` |/ _ \\ | | |",
    "| (_| | (_) || | |",
    " \\__,_|\\___/ |_| |",
])
app.set_banner(f"mytool v1.0 — zero-dep CLI")
```

Show with `TINY_CLI_SHOW_BANNER=1 mytool` or `mytool --show-banner`.

## Exit codes

Use the module-level constants instead of magic numbers:

```python
import tiny_cli as tc

@app.command()
def risky():
    if not check_preconditions():
        tc.err("preconditions not met")
        return tc.USAGE  # = 2
    return tc.OK  # = 0
```

| Constant | Value | Meaning |
|----------|-------|---------|
| `OK` | 0 | Success |
| `ERROR` | 1 | Generic failure |
| `USAGE` | 2 | Argument / parse error |
| `INTERNAL` | 3 | Internal sanitizer / config failure |
| `ABORT` | 130 | SIGINT (Ctrl-C) |

## API

| Function | Description |
|----------|-------------|
| `App(name, help, version, auto_env, env_path)` | CLI app container |
| `@app.command(name, help)` | Register a subcommand |
| `app.set_banner(text)` | Set banner text |
| `app.set_logo(lines)` | Set logo lines |
| `app.output_mode = "json"` | Switch to JSON envelope mode |
| `option(*flags, default, type, help, choices)` | Mark param as `--flag` option |
| `argument(name, type, default, help)` | Mark param as positional |
| `echo(text)` | Print to stdout (TTY-colored when available) |
| `err(text)` | Print to stderr in red |
| `confirm(question, default)` | Yes/no prompt |
| `prompt(question, type, choices, password)` | Typed prompt |
| `style.red/green/blue/bold/...` | ANSI color helpers |
| `Table(headers, theme="box")` | Themed table renderer |
| `Table.filter_cols(*names)` | Keep only named columns |
| `Table.sort_by(col, reverse=...)` | Sort rows by a column |
| `Tree(root_label="")` | ASCII tree renderer |
| `Tree.add(path, type)` | Add a `"file"\|"dir"\|"link"` node |
| `Tree.set_ascii(True)` | Force ASCII glyphs |
| `Progress(total, desc)` | Progress bar |
| `Spinner(desc)` | Animated spinner |
| `status(msg, ok=True)` | ✓/✗ one-liner |
| `load_env(path, override=False)` | Manually load a `.env` |
| `OK` / `ERROR` / `USAGE` / `INTERNAL` / `ABORT` | Exit code constants |

## Color & TTY

Colors auto-disable when stdout isn't a TTY or `NO_COLOR` env is set (12-factor friendly).

```python
tc.echo(tc.style.red("error: ", color=True) + "file not found")
```

## Agent Integration

`tiny-cli` v1.1.0 is built around three workflows that AI agents keep needing:

### 1. Programmatic invocation

Any tiny-cli app can be driven by another script or agent without parsing human output — set `output_mode = "json"` (or pass `--json`) and the app emits a single JSON line per invocation:

```python
import subprocess, json
result = subprocess.run(
    ["mytool", "greet", "alice", "--json"],
    capture_output=True, text=True,
)
envelope = json.loads(result.stdout)
# envelope == {"command": "greet", "args": {...}, "result": null, "error": null, "exit_code": 0}
```

### 2. Silent mode for tool use

When an LLM agent is calling your CLI as a "tool", set `App.output_mode = "silent"` so all status/error writes go to stderr (the agent sees stdout as the tool result):

```python
app = tc.App(name="scan", output_mode="silent")

@app.command()
def scan(target: str):
    tc.status(f"scanning {target}")  # → stderr, agent ignores
    result = do_scan(target)
    tc.echo(json.dumps(result))      # → stdout, agent reads
```

### 3. `.env` self-contained apps

Cron jobs and agent-managed tools no longer need wrapper scripts to load secrets:

```python
app = tc.App(name="nightly-report", auto_env=True)
# .env in cwd is loaded before any command runs.
```

## Agent Workflow Fit

`tiny-cli` is a good fit for the command surfaces that autonomous agents keep creating around small tools:

- **One-shot maintenance commands** — wrap cleanup, sync, scan, and report scripts with typed arguments.
- **Bounty repro CLIs** — package a reproducible exploit/checker script without adding Click or Typer.
- **Cron companions** — expose `run`, `status`, `dry-run`, and `repair` commands for scheduled jobs. `auto_env=True` lets them load secrets without a wrapper.
- **Operator prompts** — use `confirm()` and `prompt()` for rare destructive or ambiguous local actions.
- **Agent tool surface** — `output_mode = "json"` + `--json` flag turns any tiny-cli app into a clean tool for an LLM agent.

Pair it with `tiny-config` for layered settings, `tiny-log` for machine-readable output, `tiny-secret` for redacted printing, and `tiny-timeout` for commands that call flaky services.

## Reports

- [Agent operator CLIs: July 2026 field note](reports/2026-07-10-agent-operator-clis.md) — why small `run/status/doctor/repair` CLIs are becoming the local control plane for autonomous developer workflows.

## Benchmarks

```
== tiny-cli benchmarks (n=10,000) ==
  style.red                         0.173 µs/op
  style.green                       0.213 µs/op
  style.bold                        0.231 µs/op
  _coerce (int)                     0.208 µs/op
  _coerce (bool)                    0.137 µs/op
  _coerce (list)                    0.870 µs/op
  Tree.__str__ (6 entries)          8.720 µs/op
  Table.__str__ (3x5 box)           9.957 µs/op
  Table.__str__ (3x5 markdown)      9.306 µs/op
```

## Tests

```bash
python test_tiny_cli.py
# Ran 42 tests in 0.008s — OK
```

## Ecosystem

Part of the **tiny-*** zero-dependency toolkit for Python agent infrastructure:

- [**tiny-router**](https://github.com/hussain-alsaibai/tiny-router) — HTTP router, 76K req/s
- [**tiny-log**](https://github.com/hussain-alsaibai/tiny-log) — structured logging
- [**tiny-validator**](https://github.com/hussain-alsaibai/tiny-validator) — input validation, 247K val/s
- [**tiny-config**](https://github.com/hussain-alsaibai/tiny-config) — layered config loader
- [**tiny-cli**](https://github.com/hussain-alsaibai/tiny-cli) — CLI builder with colors
- [**fast-cache**](https://github.com/hussain-alsaibai/fast-cache) — LRU + TTL + SWR cache
- [**tiny-rate**](https://github.com/hussain-alsaibai/tiny-rate) — rate limiter (token / fixed / sliding)
- [**tiny-retry**](https://github.com/hussain-alsaibai/tiny-retry) — retry + backoff + circuit breaker
- [**tiny-pool**](https://github.com/hussain-alsaibai/tiny-pool) — ThreadPool + AsyncPool
- [**tiny-agent**](https://github.com/hussain-alsaibai/tiny-agent) — zero-dep agent framework
- [**tiny-mcp**](https://github.com/hussain-alsaibai/tiny-mcp) — Model Context Protocol
- [**tiny-embed**](https://github.com/hussain-alsaibai/tiny-embed) — embeddings + vector search
- [**tiny-compose**](https://github.com/hussain-alsaibai/tiny-compose) — Stack any decorators in any order, declaratively
- [**tiny-trace**](https://github.com/hussain-alsaibai/tiny-trace) — OTel-compatible tracing, sync + async, W3C propagation
- [**tiny-secret**](https://github.com/hussain-alsaibai/tiny-secret) — Zero-dep secret loader + redacting printer
- [**tiny-cron**](https://github.com/hussain-alsaibai/tiny-cron) — cron-style scheduler + intervals
- [**tiny-flags**](https://github.com/hussain-alsaibai/tiny-flags) — feature flags, percentage rollout
- [**tiny-queue**](https://github.com/hussain-alsaibai/tiny-queue) — persistent FIFO queue, retries
- [**tiny-metrics**](https://github.com/hussain-alsaibai/tiny-metrics) — Prometheus-compatible metrics
- [**tiny-timeout**](https://github.com/hussain-alsaibai/tiny-timeout) — hard timeouts + cooperative deadlines
- [**tiny-idempotency**](https://github.com/hussain-alsaibai/tiny-idempotency) — Stripe-style idempotency keys
- [**tiny-budget**](https://github.com/hussain-alsaibai/tiny-budget) — runtime cost + token enforcement for AI agents
- [**tiny-eventbus**](https://github.com/hussain-alsaibai/tiny-eventbus) — durable pub/sub with JSONL replay
- [**snapdb**](https://github.com/hussain-alsaibai/snapdb) — embedded DB

21+ repos, ~14,700 LOC, zero dependencies across the entire stack. All single-file, MIT, fully type-hinted. Built by [OpenClaw](https://github.com/hussain-alsaibai).

**New Aug 2026:** [`tiny-circuit`](https://github.com/hussain-alsaibai/tiny-circuit) — circuit breaker, [`tiny-semaphore`](https://github.com/hussain-alsaibai/tiny-semaphore) — async concurrency limiter, [`tiny-rate-limiter`](https://github.com/hussain-alsaibai/tiny-rate-limiter) — token bucket + sliding window.

## Reports

- [Agent Operator CLI Pattern](reports/2026-07-18-agent-operator-cli.md) —
  typed command boundaries for scan, verify, report, and publish loops in
  autonomous developer workflows.

## License

MIT © 2026 OpenClaw (hussain-alsaibai)
