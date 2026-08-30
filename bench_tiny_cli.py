"""Benchmarks for tiny-cli. Run with `python bench_tiny_cli.py`."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tiny_cli as tc


def bench(name, fn, n=10_000):
    fn()  # warmup
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    dt = (time.perf_counter() - t0) / n * 1e6
    print(f"  {name:30s} {dt:8.3f} µs/op")


def main():
    print("== tiny-cli benchmarks (n=10,000) ==")
    bench("style.red", lambda: tc.style.red("hi", color=True))
    bench("style.green", lambda: tc.style.green("ok", color=True))
    bench("style.bold", lambda: tc.style.bold("!!", color=True))
    bench("_coerce (int)", lambda: tc._coerce("42", int))
    bench("_coerce (bool)", lambda: tc._coerce("true", bool))
    bench("_coerce (list)", lambda: tc._coerce("a,b,c,d,e", list))

    # v1.1.0 additions
    _tree = tc.Tree(root_label="root/")
    _tree.add("src/", "dir")
    _tree.add("src/main.py", "file")
    _tree.add("src/utils.py", "file")
    _tree.add("tests/", "dir")
    _tree.add("tests/test_main.py", "file")
    _tree.add("README.md", "file")
    bench("Tree.__str__ (6 entries)", lambda: str(_tree))

    _table = tc.Table(["Name", "Size", "Modified"], theme="box")
    for n in range(5):
        _table.add_row(f"pkg-{n}", f"{n*2} KB", "2026-08-30")
    bench("Table.__str__ (3x5 box)", lambda: str(_table))

    _table2 = tc.Table(["Name", "Size", "Modified"], theme="markdown")
    for n in range(5):
        _table2.add_row(f"pkg-{n}", f"{n*2} KB", "2026-08-30")
    bench("Table.__str__ (3x5 markdown)", lambda: str(_table2))


if __name__ == "__main__":
    main()
