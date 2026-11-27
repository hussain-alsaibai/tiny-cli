"""Proof harness for tiny-cli 1.3.4's Table fixes.

Run directly:  python3 proof_1_3_4.py [--against BASE_REV]

`--against` exports that git revision of tiny_cli.py to a temp dir and runs the
same scenarios through it, so each defect is RED on the old code and GREEN on
the new one. A scenario that behaves identically on both trees is not a fix,
it is a rewrite.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# (name, callable(mod) -> short verdict string)
SCENARIOS = [
    (
        "extra-cell-is-refused",
        lambda m: run(lambda: _extra_cell(m)),
    ),
    (
        "short-row-pads-to-width",
        lambda m: run(lambda: _short_row(m)),
    ),
    (
        "column-is-sorted-by-value",
        lambda m: run(lambda: _sort(m)),
    ),
    (
        "unknown-column-is-named",
        lambda m: run(lambda: _unknown_col(m)),
    ),
    (
        "filter_keeps_align",
        lambda m: run(lambda: _align(m)),
    ),
]


def run(fn):
    try:
        return "OK " + fn()
    except Exception as exc:  # noqa: BLE001 - the type is the evidence
        return "RAISED " + type(exc).__name__ + ": " + str(exc)[:110]


def _extra_cell(m):
    t = m.Table(["A", "B"])
    t.add_row("x", "y", "z")
    return repr(t.rows)


def _short_row(m):
    t = m.Table(["A", "B", "C"])
    t.add_row("x")
    return repr(t.rows) + " widths=" + repr(t._widths)


def _sort(m):
    t = m.Table(["Name", "Size"])
    t.add_row("a", "10")
    t.add_row("b", "9")
    t.sort_by("Size")
    return repr([r[1] for r in t.rows])


def _unknown_col(m):
    t = m.Table(["Name", "Size"])
    t.add_row("a", "10")
    t.filter_cols("Name", "Typo")
    return repr(t.headers)


def _align(m):
    t = m.Table(["A", "B"], align=["r", "c"])
    t.add_row("1", "2")
    t.filter_cols("B")
    return repr(t._align)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    target = os.path.join(HERE, "tiny_cli.py")
    label = "working tree"
    if "--against" in sys.argv:
        rev = sys.argv[sys.argv.index("--against") + 1]
        tmp = tempfile.mkdtemp()
        target = os.path.join(tmp, "tiny_cli_old.py")
        blob = subprocess.run(
            ["git", "show", rev + ":tiny_cli.py"],
            cwd=HERE,
            capture_output=True,
            check=True,
        ).stdout
        with open(target, "wb") as fh:
            fh.write(blob)
        label = rev

    mod = load_module(target, "tiny_cli_probe_" + str(abs(hash(label)) % 10**6))
    print("#", label, "-", target)
    for name, fn in SCENARIOS:
        print("-", name, "->", fn(mod))


if __name__ == "__main__":
    main()
