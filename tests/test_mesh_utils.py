"""Unit tests for delorean.mesh_utils.

Not a part of the car, so most of these assert rather than render — but this
module is where nearly every real bug in this project has lived, and every one
of them was silent. A boolean that no-ops, a cutter wound the wrong way, a
solidify that folds through itself: all of them leave a mesh that is valid,
renders, and is wrong.

The tests below are named for the failures they are guarding against:

* `mesh_prism_winding` — a clockwise plan outline used to produce an inverted
  cutter, which turned a window DIFFERENCE into "keep only the cutter" and
  deleted the body down to three vertices.
* `mesh_boolean_guard` — the boolean has to notice its own failure and roll
  back, rather than handing on a mesh that is quietly empty.
* `mesh_boolean_no_growth` — neither DIFFERENCE nor INTERSECT can make a mesh
  bigger. When the FLOAT fallback merged a cutter in instead of subtracting it,
  the car's reported width jumped to the cutter's own extent.
* `mesh_solidify_manifold` — `use_even_offset` self-intersects on sharp
  creases, and the result still reports as a closed manifold.
* `mesh_assign_materials_world` — zoning read object space, so moving a door's
  origin to its hinge painted the whole panel black.
"""
from __future__ import annotations

import bpy
from mathutils import Vector

from delorean import mesh_utils as mu

from .harness import GeometryError, TestContext, visual_test

GROUP = "mesh_utils"

#: a square, counter-clockwise in the XZ plane
SQUARE = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]


def _volume(ob: bpy.types.Object) -> float:
    """Signed volume. Unsigned is useless here — the sign *is* the winding."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    v = bm.calc_volume(signed=True)
    bm.free()
    return v


def _requires_solid(ob: bpy.types.Object, label: str) -> None:
    ok, detail = mu.is_solid(ob)
    if not ok:
        raise GeometryError(f"{label}: {detail}")


# ------------------------------------------------------------------ winding
@visual_test("mesh_prism_winding", group=GROUP)
def test_prism_winding(ctx: TestContext) -> None:
    """A prism comes out wound outward whichever way its outline runs."""
    ccw = mu.prism("Prism_CCW", SQUARE, -0.5, 0.5, axis="Y")
    cw = mu.prism("Prism_CW", list(reversed(SQUARE)), -0.5, 0.5, axis="Y")

    for ob, label in ((ccw, "counter-clockwise"), (cw, "clockwise")):
        _requires_solid(ob, f"{label} prism")
        vol = _volume(ob)
        if vol <= 0.0:
            raise GeometryError(
                f"the {label} outline produced a prism of volume {vol:.6f} — "
                f"it is inside out, and any boolean using it as a cutter will "
                f"do the opposite of what was asked")

    if abs(_volume(ccw) - _volume(cw)) > 1e-9:
        raise GeometryError(
            f"winding changed the prism's volume: {_volume(ccw):.6f} vs "
            f"{_volume(cw):.6f}")
    if abs(_volume(ccw) - 1.0) > 1e-6:
        raise GeometryError(
            f"a unit prism has volume {_volume(ccw):.6f}, expected 1.0")


@visual_test("mesh_recalc_normals", group=GROUP)
def test_recalc_normals(ctx: TestContext) -> None:
    """An inside-out solid is repaired, and its signed volume comes back positive.

    This is the invariant the exact boolean solver depends on: it decides what
    is inside a mesh from the winding, so a solid whose halves disagree
    intersects correctly on one side and returns nothing on the other.
    """
    ob = mu.box("Box", (1.0, 1.0, 1.0))
    good = mu.recalc_normals(ob, outward=True)
    if abs(good - 1.0) > 1e-6:
        raise GeometryError(f"a unit box gave signed volume {good:.6f}")

    ob.data.flip_normals()
    ob.data.update()
    if _volume(ob) >= 0.0:
        raise GeometryError("flip_normals did not invert the mesh")

    repaired = mu.recalc_normals(ob, outward=True)
    if abs(repaired - good) > 1e-9:
        raise GeometryError(
            f"an inside-out box was not repaired: signed volume "
            f"{repaired:.6f}, expected {good:.6f}")
    _requires_solid(ob, "repaired box")


# ------------------------------------------------------------------ booleans
@visual_test("mesh_boolean_guard", group=GROUP)
def test_boolean_guard(ctx: TestContext) -> None:
    """A boolean that destroys its target must raise, not return an empty mesh.

    Subtracting a box from a smaller box entirely inside it leaves nothing.
    That is a legitimate arithmetic result and a nonsensical modelling one, so
    `boolean` is expected to exhaust its solvers and give up loudly.
    """
    target = mu.box("Small", (0.5, 0.5, 0.5))
    cutter = mu.box("Large", (2.0, 2.0, 2.0))

    try:
        mu.boolean(target, cutter, 'DIFFERENCE')
    except mu.BooleanError:
        return
    raise GeometryError(
        f"subtracting an enclosing box left {len(target.data.polygons)} "
        f"polygons and did not raise; a silent no-op or an empty mesh is "
        f"exactly what this guard exists to catch")


@visual_test("mesh_boolean_no_growth", group=GROUP)
def test_boolean_no_growth(ctx: TestContext) -> None:
    """DIFFERENCE and INTERSECT may only ever shrink the bounding box."""
    for operation in ('DIFFERENCE', 'INTERSECT'):
        target = mu.box(f"Target_{operation}", (1.0, 1.0, 1.0))
        before = [Vector(v.co) for v in target.data.vertices]
        lo_before = Vector((min(p.x for p in before), min(p.y for p in before),
                            min(p.z for p in before)))
        hi_before = Vector((max(p.x for p in before), max(p.y for p in before),
                            max(p.z for p in before)))

        cutter = mu.box(f"Cutter_{operation}", (0.6, 0.6, 3.0),
                        location=(0.4, 0.0, 0.0))
        mu.boolean(target, cutter, operation)

        after = [Vector(v.co) for v in target.data.vertices]
        lo = Vector((min(p.x for p in after), min(p.y for p in after),
                     min(p.z for p in after)))
        hi = Vector((max(p.x for p in after), max(p.y for p in after),
                     max(p.z for p in after)))

        for i, axis in enumerate("XYZ"):
            if lo[i] < lo_before[i] - 1e-4 or hi[i] > hi_before[i] + 1e-4:
                raise GeometryError(
                    f"{operation} grew the mesh along {axis}: "
                    f"{lo_before[i]:.4f}..{hi_before[i]:.4f} became "
                    f"{lo[i]:.4f}..{hi[i]:.4f}. The cutter was merged in "
                    f"rather than applied.")
        _requires_solid(target, f"after {operation}")


@visual_test("mesh_boolean_cuts", group=GROUP)
def test_boolean_cuts(ctx: TestContext) -> None:
    """A hole is really a hole: the material is gone, not just re-shaded."""
    target = mu.box("Slab", (1.0, 1.0, 0.2))
    cutter = mu.cylinder("Bore", 0.2, 1.0, location=(0.0, 0.0, 0.0), axis="Z")
    mu.boolean(target, cutter, 'DIFFERENCE')
    _requires_solid(target, "bored slab")

    expected = 1.0 * 1.0 * 0.2 - 3.14159 * 0.2 ** 2 * 0.2
    got = _volume(target)
    if abs(got - expected) > 0.002:
        raise GeometryError(
            f"the bored slab has volume {got:.5f}, expected about "
            f"{expected:.5f}; the bore did not remove material")

    mu.set_material(target, ctx.materials["steel"])
    ctx.render([target], "mesh_boolean_cuts", view="part_quarter", margin=1.2,
               resolution=(600, 600))


# ----------------------------------------------------------------- modifiers
@visual_test("mesh_solidify_manifold", group=GROUP)
def test_solidify_manifold(ctx: TestContext) -> None:
    """Solidify gives an open surface a wall of the thickness asked for."""
    verts, faces = [], []
    n = 12
    for i in range(n + 1):
        for j in range(n + 1):
            x = -0.5 + i / n
            y = -0.5 + j / n
            verts.append((x, y, 0.2 * (1.0 - (x * x + y * y))))
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j
            b = (i + 1) * (n + 1) + j
            faces.append((a, a + 1, b + 1, b))
    dome = mu.obj_from_pydata("Dome", verts, faces)

    mu.solidify(dome, 0.03, offset=-1.0, even=False)
    _requires_solid(dome, "solidified dome")

    inv = dome.matrix_world.inverted()
    o = inv @ Vector((0.0, 0.0, 2.0))
    d = (inv.to_3x3() @ Vector((0.0, 0.0, -1.0))).normalized()
    crossings, cursor = [], o
    for _ in range(8):
        ok, location, _n, _i = dome.ray_cast(cursor, d, distance=8.0)
        if not ok:
            break
        crossings.append(location.copy())
        cursor = location + d * 1e-4

    if len(crossings) < 2:
        raise GeometryError(
            f"a ray through the dome crosses {len(crossings)} time(s); a "
            f"walled surface gives 2")
    wall = abs(crossings[0].z - crossings[1].z)
    if abs(wall - 0.03) > 0.004:
        raise GeometryError(
            f"the wall is {wall * 1000:.1f} mm thick, expected 30.0 mm")


def _half_shell(name: str = "HalfShell") -> bpy.types.Object:
    """An open half-surface with both ends on the centreline.

    The same shape the body is: each profile starts at Y = 0, goes out and over,
    and comes back to Y = 0, so lofting gives a surface open along the
    centreline and `mirror_y` welds it into a solid.
    """
    rings = []
    for x, half_w, top in ((-0.4, 0.20, 0.30), (0.0, 0.30, 0.40), (0.4, 0.18, 0.28)):
        rings.append([(x, 0.0, 0.0), (x, half_w, 0.0),
                      (x, half_w, top), (x, 0.0, top)])
    return mu.loft(name, rings)


@visual_test("mesh_loft", group=GROUP)
def test_loft(ctx: TestContext) -> None:
    """Lofting open profiles gives an open surface — closing it is mirror_y's job.

    A ring here is a *profile*, not a loop: `loft` bridges consecutive points
    and does not join the last back to the first. Expecting a solid straight
    out of it is how you end up mirroring something that was already closed.
    """
    shell = _half_shell("Loft")
    mu.sync()

    if not shell.data.polygons:
        raise GeometryError("loft produced no faces")
    # 2 bays x 3 quads, plus a cap at each end
    if len(shell.data.polygons) != 8:
        raise GeometryError(
            f"loft gave {len(shell.data.polygons)} faces, expected 8 "
            f"(2 bays of 3 quads, plus 2 caps)")

    ok, _detail = mu.is_solid(shell)
    if ok:
        raise GeometryError(
            "the loft closed on its own; profiles are not loops, so this "
            "should be an open surface until it is mirrored")

    try:
        mu.loft("Ragged", [[(0.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
                           [(1.0, 0.0, 0.0)]])
    except ValueError:
        pass
    else:
        raise GeometryError("loft accepted rings of different lengths")


@visual_test("mesh_mirror_y", group=GROUP)
def test_mirror_y(ctx: TestContext) -> None:
    """A half becomes a symmetric solid, welded on the centreline.

    The mirrored half arrives with opposite winding. Leaving it that way is
    what makes the exact boolean read one side of the car as inside out, so
    the test checks the result is a properly wound solid, not merely symmetric.
    """
    half = _half_shell()
    before = len(half.data.vertices)
    mu.mirror_y(half)
    mu.sync()

    ys = [v.co.y for v in half.data.vertices]
    if abs(min(ys) + max(ys)) > 1e-5:
        raise GeometryError(
            f"the mirror is not symmetric: Y spans {min(ys):.5f}..{max(ys):.5f}")
    if min(ys) > -0.10:
        raise GeometryError(
            f"the mirrored half is missing: Y only reaches {min(ys):.5f}")
    if len(half.data.vertices) >= before * 2:
        raise GeometryError(
            f"{len(half.data.vertices)} vertices after mirroring {before}; "
            f"the centreline seam was not welded")

    _requires_solid(half, "mirrored half shell")

    mu.set_material(half, ctx.materials["steel"])
    ctx.render([half], "mesh_mirror_y", view="part_quarter", margin=1.2,
               resolution=(600, 600))


# ------------------------------------------------------------------ geometry
@visual_test("mesh_primitives", group=GROUP)
def test_primitives(ctx: TestContext) -> None:
    """box, cylinder, cone, prism and lathe all produce closed solids.

    `loft` is deliberately not in this list — it bridges open profiles and is
    tested in `mesh_loft`.
    """
    made = {
        "box": mu.box("P_Box", (0.4, 0.3, 0.2)),
        "cylinder": mu.cylinder("P_Cyl", 0.2, 0.5, axis="Z"),
        "cone": mu.cone("P_Cone", 0.2, 0.05, 0.4, axis="Z"),
        "prism": mu.prism("P_Prism", SQUARE, -0.2, 0.2, axis="Y"),
        "lathe": mu.lathe("P_Lathe", [(0.0, 0.0), (0.2, 0.1), (0.25, 0.3),
                                      (0.0, 0.4)], steps=24),
    }
    for label, ob in made.items():
        if not ob.data.polygons:
            raise GeometryError(f"{label} produced no faces")
        _requires_solid(ob, label)
        if _volume(ob) <= 0.0:
            raise GeometryError(
                f"{label} has volume {_volume(ob):.6f}; it is inside out")

    for ob in made.values():
        mu.set_material(ob, ctx.materials["steel"])
    ctx.render(list(made.values()), "mesh_primitives", view="part_quarter",
               margin=1.2, resolution=(700, 700))


@visual_test("mesh_offset_poly", group=GROUP)
def test_offset_poly(ctx: TestContext) -> None:
    """offset_poly grows an outline outward, which is how shut lines are made."""
    grown = mu.offset_poly(SQUARE, 0.05)
    if len(grown) != len(SQUARE):
        raise GeometryError("offset_poly changed the point count")

    span_before = max(p[0] for p in SQUARE) - min(p[0] for p in SQUARE)
    span_after = max(p[0] for p in grown) - min(p[0] for p in grown)
    if span_after <= span_before:
        raise GeometryError(
            f"offset_poly shrank the outline: {span_before:.4f} -> "
            f"{span_after:.4f}")
    if abs((span_after - span_before) / 2.0 - 0.05) > 0.002:
        raise GeometryError(
            f"offset_poly grew each side by "
            f"{(span_after - span_before) * 500:.2f} mm, expected 50.00 mm")

    shrunk = mu.offset_poly(SQUARE, -0.05)
    if max(p[0] for p in shrunk) >= max(p[0] for p in SQUARE):
        raise GeometryError("a negative offset did not shrink the outline")


@visual_test("mesh_set_origin", group=GROUP)
def test_set_origin(ctx: TestContext) -> None:
    """Moving the origin must not move the geometry.

    This is what lets a door hinge on the roof: the panel stays exactly where
    it was cut, and only its pivot changes.
    """
    ob = mu.box("Hinged", (0.4, 0.2, 0.6), location=(0.0, 0.0, 0.5))
    mu.sync()
    before = [ob.matrix_world @ Vector(v.co) for v in ob.data.vertices]

    mu.set_origin(ob, (0.0, 0.1, 1.163))
    mu.sync()
    after = [ob.matrix_world @ Vector(v.co) for v in ob.data.vertices]

    drift = max((a - b).length for a, b in zip(after, before))
    if drift > 1e-5:
        raise GeometryError(
            f"the geometry moved {drift * 1000:.3f} mm when the origin did")
    if (Vector(ob.location) - Vector((0.0, 0.1, 1.163))).length > 1e-6:
        raise GeometryError(
            f"the origin is at {tuple(round(c, 4) for c in ob.location)}, "
            f"expected (0.0, 0.1, 1.163)")


@visual_test("mesh_assign_materials_world", group=GROUP)
def test_assign_materials_world(ctx: TestContext) -> None:
    """Zoning reads world space, so it survives an origin move.

    A chooser that paints everything below Z = 0.5 black must give the same
    answer before and after the origin moves to the top of the object. Reading
    `poly.center` directly — object space — is what turned a whole door black
    once its origin went to the hinge.
    """
    steel, black = ctx.materials["steel"], ctx.materials["black"]
    chooser = lambda x, y, z: 1 if z < 0.5 else 0     # noqa: E731

    ob = mu.box("Zoned", (0.4, 0.4, 1.0), location=(0.0, 0.0, 0.5))
    mu.sync()
    mu.assign_materials(ob, [steel, black], chooser)
    before = sorted(p.material_index for p in ob.data.polygons)

    mu.set_origin(ob, (0.0, 0.0, 1.0))
    mu.sync()
    mu.assign_materials(ob, [steel, black], chooser)
    after = sorted(p.material_index for p in ob.data.polygons)

    if before != after:
        n_black_before = sum(1 for i in before if i == 1)
        n_black_after = sum(1 for i in after if i == 1)
        raise GeometryError(
            f"moving the origin changed the zoning: {n_black_before} black "
            f"faces became {n_black_after}. assign_materials is reading "
            f"object space.")

    if not any(i == 1 for i in after) or not any(i == 0 for i in after):
        raise GeometryError(
            "the chooser should have split the box across both materials")
