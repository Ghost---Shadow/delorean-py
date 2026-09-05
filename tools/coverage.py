"""Which generated geometry has a visual test, and which does not.

CLAUDE.md 9 says *every function or class that generates geometry gets a test
that renders what it produced*. That is easy to say and easy to drift from, so
this measures it.

Pure AST, system Python, no Blender: it reads the public callables out of
`delorean/` and the names actually referenced by `tests/`, and reports the
difference.

    python tools/coverage.py
    python tools/coverage.py --module doors
    python tools/coverage.py --all          # infrastructure modules too
    python tools/coverage.py --fail-under 90

What it can and cannot tell you. A name counts as covered when a test module
that imports it mentions it, so this measures *reach*, not quality:

* a name referenced by a test that fails, or that asserts nothing, still counts
* a callable reached only indirectly reads as uncovered, because the tool sees
  references rather than the call graph. `TrimBuilder.build` is the standing
  example: `build_trim` calls it and the trim tests call `build_trim`.

Treat it as a checklist of blind spots, and the suite itself as the judge of
whether anything works.
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# the Windows console defaults to cp1252 and mangles anything outside it
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "delorean"
TESTS = ROOT / "tests"

#: Modules that emit mesh data. These are the ones CLAUDE.md 9 is about, and
#: the only ones counted in the headline figure.
GEOMETRY_MODULES = ("body", "doors", "glazing", "wheels", "lamps", "trim",
                    "interior")

#: Everything else. Reported under --all, never gated: a camera rig or a
#: material has no silhouette to render, and is covered indirectly by every
#: test that stands up a scene.
SUPPORT_MODULES = ("mesh_utils", "materials", "scene", "preview", "environment",
                   "validate", "config")

#: Names that are not geometry and would only dilute the figure.
IGNORE = {"__init__", "__post_init__", "__repr__", "__str__"}


def public_callables(path: Path) -> list[str]:
    """Top-level functions and classes, plus public methods, `Class.method`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            out.append(node.name)
        elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            out.append(node.name)
            for sub in node.body:
                if (isinstance(sub, ast.FunctionDef)
                        and not sub.name.startswith("_")
                        and sub.name not in IGNORE):
                    out.append(f"{node.name}.{sub.name}")
    return out


def referenced_names(path: Path) -> set[str]:
    """Every attribute and bare name one test file mentions."""
    seen: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            seen.add(node.id)
        elif isinstance(node, ast.Attribute):
            seen.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                seen.add(alias.asname or alias.name.split(".")[-1])
    return seen


def references_by_module(importers: dict[str, set[str]]) -> dict[str, set[str]]:
    """Names mentioned by the test files that actually import each module.

    Scoping matters. Matching names globally would let `BodyBuilder.build` in
    the body tests mark `TrimBuilder.build` as covered, and the figure would
    climb while trim went untested.
    """
    per_file = {p.name: referenced_names(p) for p in test_files()}
    out: dict[str, set[str]] = {}
    for module, files in importers.items():
        names: set[str] = set()
        for name in files:
            names |= per_file.get(name, set())
        out[module] = names
    return out


def test_files() -> list[Path]:
    return sorted(TESTS.glob("test_*.py"))


def modules_under_test() -> dict[str, set[str]]:
    """module name -> the test files that import it."""
    out: dict[str, set[str]] = {}
    for path in test_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("delorean"):
                parts = (node.module or "").split(".")
                if len(parts) > 1:
                    out.setdefault(parts[1], set()).add(path.name)
                for alias in node.names:
                    out.setdefault(alias.name, set()).add(path.name)
    return out


def covered(name: str, refs: set[str]) -> bool:
    return name.split(".")[-1] in refs


def report(module_names: list[str], refs: dict[str, set[str]],
           importers: dict[str, set[str]], label: str,
           verbose: bool) -> tuple[int, int]:
    print(f"\n  {label}")
    print("  " + "-" * 74)
    total = hit = 0
    for name in module_names:
        path = PKG / f"{name}.py"
        if not path.exists():
            continue
        names = [n for n in public_callables(path) if n not in IGNORE]
        seen = refs.get(name, set())
        missing = [n for n in names if not covered(n, seen)]
        total += len(names)
        hit += len(names) - len(missing)

        pct = 100.0 * (len(names) - len(missing)) / len(names) if names else 100.0
        tests = ", ".join(sorted(importers.get(name, ()))) or "-- no test module --"
        flag = "  " if not missing else "!!"
        print(f"  {flag} {name:<12} {pct:5.1f}%  "
              f"{len(names) - len(missing):>2}/{len(names):<3} {tests}")
        if missing and verbose:
            for n in missing:
                print(f"        uncovered  {n}")
    return hit, total


def main() -> int:
    ap = argparse.ArgumentParser(prog="coverage")
    ap.add_argument("--module", default=None, help="report one module only")
    ap.add_argument("--all", action="store_true",
                    help="include support modules in the report")
    ap.add_argument("--quiet", action="store_true",
                    help="percentages only, do not list uncovered names")
    ap.add_argument("--fail-under", type=float, default=None,
                    help="exit non-zero below this geometry coverage")
    args = ap.parse_args()

    importers = modules_under_test()
    refs = references_by_module(importers)
    verbose = not args.quiet

    print("\n  visual test coverage — public callables referenced by tests/")

    geometry = ([args.module] if args.module else list(GEOMETRY_MODULES))
    hit, total = report(geometry, refs, importers, "geometry", verbose)

    if args.all and not args.module:
        report(list(SUPPORT_MODULES), refs, importers,
               "support (not gated)", verbose)

    pct = 100.0 * hit / total if total else 100.0
    print("\n  " + "-" * 74)
    print(f"  geometry coverage {pct:.1f}%  ({hit}/{total} callables)"
          f"   {len(test_files())} test module(s)\n")

    if args.fail_under is not None and pct < args.fail_under:
        print(f"  FAIL: below --fail-under {args.fail_under:.1f}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
