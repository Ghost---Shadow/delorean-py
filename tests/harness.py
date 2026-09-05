"""Visual unit tests.

A geometry bug is almost never visible in a number, and almost always obvious in
a picture. So every test here does two things:

  1. **Asserts** what can be asserted — bounding box, watertightness, loose
     geometry, material assignment. These fail the run.
  2. **Renders** what the function under test actually produced, isolated and
     tightly framed, next to its reference crop. These are for the eye.

Tests build their part into a *fresh* scene, so a test exercises the real
construction path rather than poking at an already-built car.

Run them all:

    blender -b -P tests/run_tests.py
    blender -b -P tests/run_tests.py -- --only wheel
"""
from __future__ import annotations

import math
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Callable

import bpy

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from delorean import config as cfg           # noqa: E402
from delorean import mesh_utils as mu        # noqa: E402
from delorean import preview                 # noqa: E402
from delorean.materials import MaterialLibrary  # noqa: E402
from delorean.scene import BACKDROP_BLUEPRINT, SceneBuilder  # noqa: E402

OUT_DIR = os.path.join(_ROOT, "renders", "tests")
REF_PARTS = os.path.join(_ROOT, "references", "parts")


# ============================================================================
#  context handed to each test
# ============================================================================
@dataclass
class TestContext:
    """A fresh scene, a material library and a camera rig."""

    materials: MaterialLibrary
    scene: SceneBuilder
    build_cfg: cfg.BuildConfig

    def render(self, objects, name: str, view: str = "hero_front_left",
               margin: float = 1.15, resolution: tuple[int, int] = (760, 760),
               samples: int = 24, keep_ground: bool = False) -> str:
        path = os.path.join(OUT_DIR, f"{name}.png")
        return preview.preview_part(self.scene, objects, path, view=view,
                                    margin=margin, resolution=resolution,
                                    samples=samples, keep_ground=keep_ground)


# ============================================================================
#  assertions
# ============================================================================
class GeometryError(AssertionError):
    """A structural problem with generated geometry."""


def assert_dimensions(ob: bpy.types.Object, expected: tuple[float, float, float],
                      tol: float = 0.02, label: str = "") -> None:
    got = tuple(round(v, 4) for v in ob.dimensions)
    for axis, g, e in zip("XYZ", got, expected):
        if e is None:
            continue
        if abs(g - e) > tol:
            raise GeometryError(
                f"{label or ob.name}: {axis} is {g:.4f} m, expected "
                f"{e:.4f} +/- {tol} m")


def assert_no_loose_geometry(ob: bpy.types.Object) -> None:
    me = ob.data
    used_v = {i for p in me.polygons for i in p.vertices}
    loose_v = len(me.vertices) - len(used_v)
    if loose_v:
        raise GeometryError(f"{ob.name}: {loose_v} loose vertices")

    face_edges = set()
    for p in me.polygons:
        face_edges.update(p.edge_keys)
    loose_e = sum(1 for e in me.edges if e.key not in face_edges)
    if loose_e:
        raise GeometryError(f"{ob.name}: {loose_e} loose edges")


def assert_no_degenerate_faces(ob: bpy.types.Object, min_area: float = 1e-9) -> None:
    bad = [p.index for p in ob.data.polygons if p.area < min_area]
    if bad:
        raise GeometryError(
            f"{ob.name}: {len(bad)} zero-area faces (first at index {bad[0]})")


def assert_has_material(ob: bpy.types.Object) -> None:
    if not ob.data.materials or all(m is None for m in ob.data.materials):
        raise GeometryError(f"{ob.name}: no material assigned")


def assert_non_empty(ob: bpy.types.Object, min_polys: int = 1) -> None:
    n = len(ob.data.polygons)
    if n < min_polys:
        raise GeometryError(f"{ob.name}: {n} polygons, expected >= {min_polys}")


def assert_within_bounds(objects, lo: tuple, hi: tuple, label: str = "") -> None:
    """Every vertex sits inside an axis-aligned box. None disables an axis."""
    from mathutils import Vector
    mu.sync()
    for ob in objects:
        if ob.type != 'MESH':
            continue
        for v in ob.data.vertices:
            p = ob.matrix_world @ Vector(v.co)
            for i, axis in enumerate("XYZ"):
                if lo[i] is not None and p[i] < lo[i] - 1e-4:
                    raise GeometryError(
                        f"{label or ob.name}: vertex {axis}={p[i]:.4f} below "
                        f"limit {lo[i]:.4f}")
                if hi[i] is not None and p[i] > hi[i] + 1e-4:
                    raise GeometryError(
                        f"{label or ob.name}: vertex {axis}={p[i]:.4f} above "
                        f"limit {hi[i]:.4f}")


def standard_checks(objects, min_polys: int = 4) -> None:
    """The checks every generated part should survive."""
    mu.sync()
    for ob in objects:
        if ob.type != 'MESH':
            continue
        assert_non_empty(ob, min_polys)
        assert_no_loose_geometry(ob)
        assert_no_degenerate_faces(ob)
        assert_has_material(ob)


# ============================================================================
#  registry
# ============================================================================
@dataclass
class VisualTest:
    name: str
    fn: Callable[[TestContext], None]
    reference: str | None = None
    group: str = "misc"
    doc: str = ""


REGISTRY: list[VisualTest] = []


def visual_test(name: str, reference: str | None = None, group: str = "misc"):
    """Register a test. `reference` is a path under references/parts/."""
    def deco(fn):
        REGISTRY.append(VisualTest(name=name, fn=fn, reference=reference,
                                   group=group, doc=(fn.__doc__ or "").strip()))
        return fn
    return deco


# ============================================================================
#  runner
# ============================================================================
def fresh_scene(build_cfg: cfg.BuildConfig | None = None) -> TestContext:
    """Wipe everything and stand up a minimal lit scene."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                  bpy.data.cameras, bpy.data.curves):
        for item in list(block):
            block.remove(item)

    coll = bpy.data.collections.new("TestPart")
    bpy.context.scene.collection.children.link(coll)
    mu.set_target_collection(coll)

    build_cfg = build_cfg or cfg.BuildConfig()
    materials = MaterialLibrary()
    scene = SceneBuilder(materials, build_cfg,
                         backdrop=BACKDROP_BLUEPRINT)
    scene.world()
    scene.lights()
    scene.camera_rig()
    scene.render_settings(resolution=(760, 760), samples=24)
    return TestContext(materials=materials, scene=scene, build_cfg=build_cfg)


@dataclass
class Result:
    name: str
    group: str
    passed: bool
    seconds: float
    message: str = ""
    renders: list[str] = field(default_factory=list)


def run(selection: str | None = None) -> list[Result]:
    os.makedirs(OUT_DIR, exist_ok=True)
    results: list[Result] = []

    tests = [t for t in REGISTRY
             if selection is None or selection.lower() in t.name.lower()
             or selection.lower() in t.group.lower()]

    for test in tests:
        started = time.time()
        before = set(os.listdir(OUT_DIR))
        try:
            ctx = fresh_scene()
            test.fn(ctx)
            ok, msg = True, ""
        except Exception as exc:                      # noqa: BLE001
            ok = False
            msg = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        after = set(os.listdir(OUT_DIR))
        results.append(Result(
            name=test.name, group=test.group, passed=ok,
            seconds=time.time() - started, message=msg,
            renders=sorted(after - before)))
    return results


def report(results: list[Result]) -> bool:
    width = max((len(r.name) for r in results), default=10) + 2
    print("\n" + "=" * (width + 34))
    print("visual unit tests".center(width + 34))
    print("=" * (width + 34))
    group = None
    for r in results:
        if r.group != group:
            group = r.group
            print(f"\n  [{group}]")
        mark = "PASS" if r.passed else "FAIL"
        print(f"    {mark}  {r.name:<{width}} {r.seconds:6.2f}s"
              + (f"  {len(r.renders)} render(s)" if r.renders else ""))
        if not r.passed:
            print(f"          {r.message}")

    failed = [r for r in results if not r.passed]
    print("\n" + "-" * (width + 34))
    print(f"  {len(results) - len(failed)}/{len(results)} passed"
          f"    renders -> {os.path.relpath(OUT_DIR, _ROOT)}")
    print("-" * (width + 34) + "\n")
    return not failed
