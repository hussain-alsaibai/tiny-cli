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


if __name__ == "__main__":
    main()
