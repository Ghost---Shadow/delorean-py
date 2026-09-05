"""Post-build assertions.

"Perfect every time" needs teeth. A boolean that silently no-ops, an arch that
misses, a wheel that floats — none of those raise on their own. They have to be
caught here, or the build quietly produces a slightly wrong car.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import bpy
from mathutils import Vector

from . import config as cfg
from . import mesh_utils as mu


class ValidationError(AssertionError):
    """The build produced something that is not a DeLorean."""


@dataclass
class Report:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))

    @property
    def failures(self) -> list[tuple[str, bool, str]]:
        return [c for c in self.checks if not c[1]]

    @property
    def ok(self) -> bool:
        return not self.failures

    def render(self) -> str:
        width = max(len(c[0]) for c in self.checks) + 2
        lines = ["", "  validation", "  " + "-" * (width + 30)]
        for name, ok, detail in self.checks:
            mark = "ok  " if ok else "FAIL"
            lines.append(f"  {mark} {name:<{width}} {detail}")
        lines.append("  " + "-" * (width + 30))
        lines.append(f"  {len(self.checks) - len(self.failures)}"
                     f"/{len(self.checks)} checks passed")
        return "\n".join(lines) + "\n"


def _world_bounds(objects) -> tuple[Vector, Vector]:
    """Extents from actual vertices.

    Deliberately not `bound_box`: that is cached and goes stale after a boolean
    replaces the mesh, which silently reports a car a metre too short.
    """
    lo = Vector((1e9, 1e9, 1e9))
    hi = Vector((-1e9, -1e9, -1e9))
    for ob in objects:
        if ob.type != 'MESH':
            continue
        mat = ob.matrix_world
        for v in ob.data.vertices:
            p = mat @ v.co
            for i in range(3):
                lo[i] = min(lo[i], p[i])
                hi[i] = max(hi[i], p[i])
    return lo, hi


def validate(objects: list[bpy.types.Object], rig: cfg.RigConfig,
             strict: bool = True) -> Report:
    mu.sync()
    report = Report()
    meshes = [o for o in objects if o.type == 'MESH']

    # ---- overall dimensions against the published car
    body_like = [o for o in meshes
                 if not o.name.startswith(("Ground", "Glass_"))]
    lo, hi = _world_bounds(body_like)
    size = hi - lo
    doors_shut = rig.door_angle_deg < 1.0

    for axis, got, want, tol in (
            ("length", size.x, cfg.LENGTH, 0.030),
            ("width", size.y, cfg.WIDTH, 0.030),
            ("height", size.z, cfg.HEIGHT, 0.030)):
        if axis == "height" and not doors_shut:
            report.add(f"overall {axis}", True,
                       f"{got:.3f} m (doors open, not checked)")
            continue
        ok = abs(got - want) <= tol
        report.add(f"overall {axis}", ok,
                   f"{got:.3f} m, expected {want:.3f} +/- {tol:.3f}")

    # ---- the car sits on the ground
    tyres = [o for o in meshes if o.name.endswith("_Tyre") and o.data.vertices]
    if tyres:
        lowest = min(min((o.matrix_world @ v.co).z for v in o.data.vertices)
                     for o in tyres)
        report.add("wheels on ground", abs(lowest) < 0.004,
                   f"lowest tyre point {lowest * 1000:+.1f} mm")

    # ---- nothing pokes through the floor
    below = [o.name for o in body_like if o.data.vertices
             and min((o.matrix_world @ v.co).z for v in o.data.vertices) < -0.005]
    report.add("nothing below ground", not below, ", ".join(below[:3]))

    # ---- mesh hygiene
    bad_loose, bad_degenerate, bad_material, empty = [], [], [], []
    for ob in meshes:
        me = ob.data
        if not me.polygons:
            empty.append(ob.name)
            continue
        used = {i for p in me.polygons for i in p.vertices}
        if len(me.vertices) - len(used) > 0:
            bad_loose.append(ob.name)
        if any(p.area < 1e-9 for p in me.polygons):
            bad_degenerate.append(ob.name)
        if not me.materials or all(m is None for m in me.materials):
            bad_material.append(ob.name)

    report.add("no empty meshes", not empty, ", ".join(empty[:3]))
    report.add("no loose vertices", not bad_loose, ", ".join(bad_loose[:3]))
    report.add("no zero-area faces", not bad_degenerate,
               ", ".join(bad_degenerate[:3]))
    report.add("every object has a material", not bad_material,
               ", ".join(bad_material[:3]))

    # ---- the pieces that must exist
    names = {o.name for o in objects}
    required = {"Body", "Door_L", "Door_R",
                "Wheel_FL_Tyre", "Wheel_FR_Tyre",
                "Wheel_RL_Tyre", "Wheel_RR_Tyre",
                "Glass_Windscreen", "Glass_Backlight"}
    missing = sorted(required - names)
    report.add("expected objects present", not missing, ", ".join(missing))

    # ---- the doors actually came out of the shell
    for side in ("L", "R"):
        door = bpy.data.objects.get(f"Door_{side}")
        ok = door is not None and len(door.data.polygons) > 40
        n = len(door.data.polygons) if door else 0
        report.add(f"door {side} has geometry", ok, f"{n} polygons")

    if strict and not report.ok:
        raise ValidationError(
            "build failed validation:\n" +
            "\n".join(f"  - {n}: {d}" for n, _, d in report.failures))
    return report
