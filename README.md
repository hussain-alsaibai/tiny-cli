# tiny-cli

> Zero-dependency CLI builder for Python. Decorators, color, prompts — argparse without the bloat.

```bash
pip install tiny-cli   # coming soon
```

## Why?

- **`argparse`** — verbose, no colors, no prompts
- **`click`** — 1 dep (`markupsafe`), heavy
- **`typer`** — 6 deps, requires pydantic + click

**tiny-cli** is ~250 lines, zero deps, gives you the 90% case: commands, options, color, prompts.

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

## API

| Function | Description |
|----------|-------------|
| `App(name, help, version)` | CLI app container |
| `@app.command(name, help)` | Register a subcommand |
| `option(*flags, default, type, help, choices)` | Mark param as `--flag` option |
| `argument(name, type, default, help)` | Mark param as positional |
| `echo(text)` | Print to stdout (TTY-colored when available) |
| `confirm(question, default)` | Yes/no prompt |
| `prompt(question, type, choices, password)` | Typed prompt |
| `style.red/green/blue/bold/...` | ANSI color helpers |

## Color & TTY

Colors auto-disable when stdout isn't a TTY or `NO_COLOR` env is set (12-factor friendly).

```python
tc.echo(tc.style.red("error: ", color=True) + "file not found")
```

## Benchmarks

```
== tiny-cli benchmarks (n=10,000) ==
  style.red                       0.214 µs/op
  style.green                     0.207 µs/op
  style.bold                      0.211 µs/op
  _coerce (int)                   0.487 µs/op
  _coerce (bool)                  0.391 µs/op
  _coerce (list)                  3.142 µs/op
```

## Tests

```bash
python test_tiny_cli.py
# Ran 14 tests in 0.004s — OK
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
- [**snapdb**](https://github.com/hussain-alsaibai/snapdb) — embedded DB

12 repos, ~5,200 LOC, zero dependencies across the entire stack. All single-file, MIT, fully type-hinted. Built by [OpenClaw](https://github.com/hussain-alsaibai).
## License

MIT © 2026 OpenClaw (hussain-alsaibai)
