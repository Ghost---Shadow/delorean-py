"""Visual unit tests for delorean.doors.

References: references/parts/doors/door-gullwing-open.png,
            references/parts/doors/door-inner-hinge.png,
            references/parts/doors/door-sill-jamb.png

The doors are cut out of the finished shell rather than modelled separately, so
every test here builds a real body first. That makes these the slowest tests in
the suite, and it is unavoidable: a door tested against anything except the
shell it came from proves nothing about whether it fits.

Several of these are regression tests for bugs that shipped silently, because a
failed boolean leaves a valid-looking mesh behind:

* `door_panel_pair` pins the outboard extent to the body's half width. When a
  DIFFERENCE falls back to the FLOAT solver and merges the cutter in instead of
  subtracting it, the panel reaches DOOR_OUTBOARD (1.350 m) and nothing else
  notices.
* `door_aperture_open` casts a ray through the hole. A boolean that quietly
  returns the original mesh leaves the body closed, and the door then sits on
  top of an unbroken flank.
* `door_material_zoning` checks the panel is mostly steel. Zoning reads world
  coordinates; when it read object space instead, moving the origin to the
  hinge at z = 1.163 dropped every face a metre and turned the whole door black.
"""
from __future__ import annotations

import math

import bpy
from mathutils import Vector

from delorean import body as body_mod
from delorean import config as cfg
from delorean import doors as doors_mod
from delorean import mesh_utils as mu
from delorean.doors import (DOOR_OUTBOARD, DOOR_OUTLINE, HINGE_Y, HINGE_Z,
                            SPINE_HALF_WIDTH, WINDOW_OUTLINE, DoorBuilder,
                            pose_doors)

from .harness import (GeometryError, TestContext, assert_within_bounds,
                      standard_checks, visual_test)

GROUP = "doors"

#: half the body's beam, which is where the outer door skin has to land
BODY_HALF_WIDTH = cfg.WIDTH / 2.0


# ------------------------------------------------------------------ fixtures
def _split(ctx: TestContext):
    """A finished shell and both door panels cut out of it."""
    shell = body_mod.BodyBuilder(ctx.materials).build()
    doors = DoorBuilder(ctx.materials).split(shell)
    mu.sync()
    return shell, doors


def _world_verts(ob: bpy.types.Object) -> list[Vector]:
    return [ob.matrix_world @ Vector(v.co) for v in ob.data.vertices]


def _centroid(outline) -> tuple[float, float]:
    return (sum(p[0] for p in outline) / len(outline),
            sum(p[1] for p in outline) / len(outline))


def _hits(ob: bpy.types.Object, origin: Vector, direction: Vector) -> int:
    """How many times a world-space ray crosses `ob`'s surface.

    Object-space, because `ray_cast` is: a door whose origin has moved to the
    hinge would otherwise be probed a metre off.
    """
    inv = ob.matrix_world.inverted()
    o = inv @ origin
    d = (inv.to_3x3() @ direction).normalized()
    count, cursor = 0, o
    for _ in range(12):                     # generous; a solid slab gives 2
        ok, location, _n, _i = ob.ray_cast(cursor, d, distance=12.0)
        if not ok:
            break
        count += 1
        cursor = location + d * 1e-4
    return count


# ---------------------------------------------------------------- the panels
@visual_test("door_panel_pair", reference="doors/door-gullwing-open.png",
             group=GROUP)
def test_panel_pair(ctx: TestContext) -> None:
    """Two panels, cut to the door outline, flush with the flank."""
    _shell, doors = _split(ctx)

    standard_checks(doors, min_polys=20)
    if len(doors) != 2:
        raise GeometryError(f"expected 2 doors, got {len(doors)}")
    if {d.name for d in doors} != {"Door_L", "Door_R"}:
        raise GeometryError(f"unexpected names: {[d.name for d in doors]}")

    xs = [p[0] for p in DOOR_OUTLINE]
    zs = [p[1] for p in DOOR_OUTLINE]
    assert_within_bounds(doors,
                         lo=(min(xs) - 0.002, None, min(zs) - 0.002),
                         hi=(max(xs) + 0.002, None, max(zs) + 0.002),
                         label="door outline")

    for door in doors:
        ys = [abs(p.y) for p in _world_verts(door)]
        # inboard: the panel stops at the spine, leaving the centre T-bar
        if min(ys) < SPINE_HALF_WIDTH - 0.002:
            raise GeometryError(
                f"{door.name} reaches |Y|={min(ys):.4f} m, inside the "
                f"{SPINE_HALF_WIDTH:.3f} m spine")
        # outboard: the panel is clipped by the body, NOT by its own cutter.
        # Reaching DOOR_OUTBOARD means the boolean merged the cutter in.
        if max(ys) > BODY_HALF_WIDTH + 0.004:
            raise GeometryError(
                f"{door.name} reaches |Y|={max(ys):.4f} m, past the body's "
                f"{BODY_HALF_WIDTH:.4f} m half width (the cutter extends to "
                f"{DOOR_OUTBOARD:.3f} m — the boolean merged it in)")
        if max(ys) < BODY_HALF_WIDTH - 0.020:
            raise GeometryError(
                f"{door.name} only reaches |Y|={max(ys):.4f} m; it is sunk "
                f"into the flank rather than flush with it")

    ctx.render(doors, "door_panel_pair", view="part_quarter", margin=1.2)
    ctx.render([doors[0]], "door_panel_left", view="side", margin=1.15,
               resolution=(900, 620))


@visual_test("door_panel_watertight", group=GROUP)
def test_panel_watertight(ctx: TestContext) -> None:
    """Both panels must close, and must be mirror images of one another.

    The two doors are cut with mirrored copies of a single outline, so any
    difference in their topology is the boolean solver behaving differently on
    the two sides. That is never intentional, and an unclosed panel is what
    later booleans choke on.
    """
    _shell, doors = _split(ctx)

    broken = [f"{d.name}: {detail}" for d in doors
              for ok, detail in [mu.is_solid(d)] if not ok]
    if broken:
        raise GeometryError("; ".join(broken))

    left, right = sorted(doors, key=lambda d: d.name)
    if len(left.data.polygons) != len(right.data.polygons):
        raise GeometryError(
            f"the doors are not mirror images: {left.name} has "
            f"{len(left.data.polygons)} faces, {right.name} has "
            f"{len(right.data.polygons)}")


@visual_test("door_window_aperture", group=GROUP)
def test_window_aperture(ctx: TestContext) -> None:
    """The daylight opening is a through-hole, and only where it should be."""
    _shell, doors = _split(ctx)
    door = next(d for d in doors if d.name.endswith("_L"))

    x, z = _centroid(WINDOW_OUTLINE)
    across = Vector((0.0, -1.0, 0.0))

    open_hits = _hits(door, Vector((x, 2.0, z)), across)
    if open_hits:
        raise GeometryError(
            f"the window at (x={x:.3f}, z={z:.3f}) is not open: a ray across "
            f"the car hits the panel {open_hits} time(s)")

    # control: the solid panel below the sill line must be hit twice, outer
    # skin then inner. Zero here would mean the panel is missing entirely.
    solid_hits = _hits(door, Vector((x, 2.0, 0.60)), across)
    if solid_hits < 2:
        raise GeometryError(
            f"the panel below the window is not solid: {solid_hits} hit(s), "
            f"expected 2 (outer skin then inner)")

    ctx.render([door], "door_window_aperture", view="side", margin=1.15,
               resolution=(900, 620))


@visual_test("door_aperture_open", reference="doors/door-sill-jamb.png",
             group=GROUP)
def test_aperture_open(ctx: TestContext) -> None:
    """The shell keeps a hole the shape of the door it gave up."""
    shell, doors = _split(ctx)

    xs = [p[0] for p in DOOR_OUTLINE]
    x = sum(xs) / len(xs)
    hits = _hits(shell, Vector((x, 2.0, 0.60)), Vector((0.0, -1.0, 0.0)))
    if hits:
        raise GeometryError(
            f"the door aperture is closed: a ray across the car at x={x:.3f} "
            f"hits the shell {hits} time(s). The DIFFERENCE returned the "
            f"original mesh.")

    ctx.render([shell], "door_aperture_open", view="hero_front_left",
               margin=1.1, resolution=(900, 620))
    ctx.render([shell] + doors, "door_aperture_fitted", view="part_quarter",
               margin=1.2)


@visual_test("door_centre_spine", group=GROUP)
def test_centre_spine(ctx: TestContext) -> None:
    """The T-bar down the middle survives both cuts.

    A DMC-12 hinges on the roof, so each door takes a slice of it with it. What
    is left between them is the centre spine; cut that away and the two door
    apertures merge into one hole where the roof used to be.
    """
    shell, _doors = _split(ctx)

    spine = [p for p in _world_verts(shell)
             if abs(p.y) < SPINE_HALF_WIDTH - 0.005 and p.z > 1.00]
    if len(spine) < 8:
        raise GeometryError(
            f"only {len(spine)} shell vertices left in the roof spine "
            f"(|Y| < {SPINE_HALF_WIDTH:.3f} m, Z > 1.00 m); the two door cuts "
            f"have met in the middle")

    ctx.render([shell], "door_centre_spine", view="part_top", margin=1.05,
               resolution=(900, 700))


@visual_test("door_material_zoning", group=GROUP)
def test_material_zoning(ctx: TestContext) -> None:
    """Steel above, black urethane along the sill — in world coordinates.

    Zoning is applied after the origin has moved to the hinge. Reading object
    space there puts every face a metre low and paints the whole panel black.
    """
    _shell, doors = _split(ctx)
    door = doors[0]

    slots = [m.name for m in door.data.materials]
    if len(slots) < 2:
        raise GeometryError(
            f"{door.name}: material slots {slots}, expected steel and black")

    counts: dict[int, int] = {}
    for poly in door.data.polygons:
        counts[poly.material_index] = counts.get(poly.material_index, 0) + 1
    steel = counts.get(0, 0)
    total = sum(counts.values())
    if steel / total < 0.60:
        raise GeometryError(
            f"{door.name}: only {100.0 * steel / total:.0f}% of faces are "
            f"steel. The door sits almost entirely above the rocker line and "
            f"should be largely bare metal — zoning is reading object space.")

    ctx.render(doors, "door_material_zoning", view="part_quarter", margin=1.2)


# ------------------------------------------------------------------- the rig
@visual_test("door_hinge_pose", reference="doors/door-inner-hinge.png",
             group=GROUP)
def test_hinge_pose(ctx: TestContext) -> None:
    """Opening is one rotation about the roof hinge, opposite on each side."""
    _shell, doors = _split(ctx)

    for door in doors:
        sign = 1.0 if door.name.endswith("_L") else -1.0
        expected = Vector((0.0, sign * HINGE_Y, HINGE_Z))
        if (Vector(door.location) - expected).length > 1e-6:
            raise GeometryError(
                f"{door.name} origin at "
                f"{tuple(round(c, 4) for c in door.location)}, expected the "
                f"hinge at {tuple(round(c, 4) for c in expected)}")

    shut_top = {d.name: max(p.z for p in _world_verts(d)) for d in doors}

    angle = 48.0
    pose_doors(doors, cfg.RigConfig(door_angle_deg=angle))

    for door in doors:
        sign = 1.0 if door.name.endswith("_L") else -1.0
        rot = door.rotation_euler
        if abs(rot.x - sign * math.radians(angle)) > 1e-6:
            raise GeometryError(
                f"{door.name}: X rotation {math.degrees(rot.x):.2f} deg, "
                f"expected {sign * angle:.2f}")
        if abs(rot.y) > 1e-9 or abs(rot.z) > 1e-9:
            raise GeometryError(
                f"{door.name}: opening is not a pure X rotation ({rot[:]})")
        if (Vector(door.location)
                - Vector((0.0, sign * HINGE_Y, HINGE_Z))).length > 1e-6:
            raise GeometryError(f"{door.name}: the hinge moved when it opened")

        risen = max(p.z for p in _world_verts(door))
        if risen <= shut_top[door.name] + 0.10:
            raise GeometryError(
                f"{door.name} rose only "
                f"{(risen - shut_top[door.name]) * 1000:.0f} mm at "
                f"{angle:.0f} deg; it is rotating the wrong way")

    ctx.render(doors, "door_hinge_pose", view="front", margin=1.2,
               resolution=(900, 700))


@visual_test("door_gullwing_open", reference="doors/door-gullwing-open.png",
             group=GROUP)
def test_gullwing_open(ctx: TestContext) -> None:
    """Both doors up on the shell they came from.

    The published doors-open height is 1962 mm over the mirror, which the
    mirror contributes to and the shell alone cannot reach; this checks the
    panels stay under it rather than trying to hit it.
    """
    shell = body_mod.BodyBuilder(ctx.materials).build()
    doors = doors_mod.build_doors(shell, ctx.materials,
                                  cfg.RigConfig.doors_open(52.0))
    mu.sync()

    standard_checks(doors, min_polys=20)

    top = max(p.z for d in doors for p in _world_verts(d))
    if top > cfg.HEIGHT_DOORS_OPEN:
        raise GeometryError(
            f"doors reach {top * 1000:.0f} mm at 52 deg, over the published "
            f"{cfg.HEIGHT_DOORS_OPEN * 1000:.0f} mm doors-open height")
    if top < cfg.HEIGHT + 0.20:
        raise GeometryError(
            f"doors reach only {top * 1000:.0f} mm, barely over the "
            f"{cfg.HEIGHT * 1000:.0f} mm roof; they are not opening")

    ctx.render([shell] + doors, "door_gullwing_open", view="hero_front_left",
               margin=1.15, resolution=(960, 660))
    ctx.render([shell] + doors, "door_gullwing_front", view="front",
               margin=1.15, resolution=(900, 700))
