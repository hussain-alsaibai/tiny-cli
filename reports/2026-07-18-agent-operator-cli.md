# Agent Operator CLI Pattern - July 18, 2026

## Signal

Developer tools are moving from one-shot command helpers toward repeatable
operator loops: scan, score, run, verify, report, and hand off. The useful CLI
surface for an autonomous coding agent is not a large framework; it is a small
set of typed commands that are easy to audit and safe to compose in cron jobs.

## Pattern

Use `tiny-cli` for narrow operator commands:

```python
from tiny_cli import cli


@cli
def scan(repo: str, min_score: int = 50, dry_run: bool = True):
    """Scan a repo and print ranked work candidates."""
    ...


@cli
def report(thread_id: int, since_hours: int = 24):
    """Summarize completed autonomous work."""
    ...


if __name__ == "__main__":
    cli.run()
```

The command line becomes the boundary between the scheduler and the work:

```bash
python operator.py scan hussain-alsaibai/dev-masterkit --min-score 70
python operator.py report --thread-id 17 --since-hours 24
```

## Design Rules

- Keep every command idempotent or explicitly mark it as a side effect.
- Give destructive or public commands a `dry_run` default where possible.
- Prefer typed scalar flags over JSON blobs at the CLI layer.
- Return machine-readable output for cron and human-readable output for manual
  runs.
- Keep command names boring: `scan`, `verify`, `report`, `publish`, `sync`.

## Why `tiny-cli`

Agent workflows fail quietly when orchestration is hidden inside long shell
scripts. `tiny-cli` gives each operation a function signature, docstring help,
and predictable flag parsing without pulling in Click, Typer, or an application
framework.

For OpenClaw-style work, that means bounty scanners, repo monitors, update
checks, and report publishers can share one shape:

1. typed inputs,
2. focused side effects,
3. testable functions,
4. cron-friendly execution.

## Companion Tools

- `tiny-config` for repo lists, thresholds, and destination routing.
- `tiny-log` for structured evidence of each command run.
- `tiny-validator` for validating message payloads before sending.
- `tiny-budget` for bounding model or API spend per command.

## Last Verified

2026-07-18 - created during the developer tool reports cron after reviewing
2026 agent infrastructure trends around CLI coding agents, orchestration loops,
and lightweight local automation.
