"""Entry point for the visual unit tests.

    blender -b -P tests/run_tests.py
    blender -b -P tests/run_tests.py -- --only wheel

Also safe to exec from an interactive Blender session: it reloads the package
from disk each time and returns the results instead of killing the process.
"""
from __future__ import annotations

import argparse
import importlib
import os
import pkgutil
import sys

import bpy

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _purge_modules() -> None:
    """Drop cached modules so an interactive re-exec picks up file edits."""
    for name in [m for m in sys.modules
                 if m == "delorean" or m.startswith("delorean.")
                 or m == "tests" or m.startswith("tests.")]:
        del sys.modules[name]


def _discover() -> None:
    import tests as pkg
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("test_"):
            importlib.import_module("tests." + mod.name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_tests")
    ap.add_argument("--only", default=None,
                    help="substring filter on test name or group")
    args = ap.parse_args(argv or [])

    _purge_modules()
    from tests import harness

    _discover()
    results = harness.run(args.only)
    return 0 if harness.report(results) else 1


def _cli_args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


if __name__ == "__main__":
    code = main(_cli_args())
    if bpy.app.background:
        sys.exit(code)
