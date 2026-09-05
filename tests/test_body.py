"""Visual unit tests for delorean.body.

References: references/parts/body/swage-line-flank.png,
            references/parts/body/arch-rear-wheel.png

The shell is the foundation every later boolean stands on, so these tests are
as much about *validity* as about shape. `BodyBuilder` already asserts
`is_solid` at each stage; what it cannot check is whether the result matches
the published car, or whether the hand-authored station table still makes
sense after an edit.

The surface-query tests are pure arithmetic and cost nothing. They are worth
having because `station_at`, `skin_z_at` and `flank_half_width` are consumed by
glazing, trim and the interior — a bad station silently moves the windscreen,
the louvres and the door glass all at once.
"""
from __future__ import annotations

import bpy
from mathutils import Vector

from delorean import body as body_mod
from delorean import config as cfg
from delorean import mesh_utils as mu
from delorean.body import (STATIONS, BodyBuilder, Station, flank_half_width,
                           is_black_trim, nose_x, polygon_span, skin_patch,
                           skin_point, skin_z_at, station_at, tail_x,
                           zone_body_materials)

from .harness import (GeometryError, TestContext, assert_dimensions,
                      standard_checks, visual_test)

GROUP = "body"


def _world_verts(ob: bpy.types.Object) -> list[Vector]:
    return [ob.matrix_world @ Vector(v.co) for v in ob.data.vertices]


def _hits(ob: bpy.types.Object, origin: Vector, direction: Vector) -> list[Vector]:
    """Where a world-space ray crosses `ob`, in order."""
    inv = ob.matrix_world.inverted()
    o = inv @ origin
    d = (inv.to_3x3() @ direction).normalized()
    out: list[Vector] = []
    cursor = o
    for _ in range(16):
        ok, location, _n, _i = ob.ray_cast(cursor, d, distance=12.0)
        if not ok:
            break
        out.append(ob.matrix_world @ location)
        cursor = location + d * 1e-4
    return out


# --------------------------------------------------------- the station table
@visual_test("body_station_table", group=GROUP)
def test_station_table(ctx: TestContext) -> None:
    """The hand-authored cross sections must stay ordered and plausible.

    21 records of 8 numbers each, edited by hand. A station out of order makes
    the loft fold back on itself, and the resulting mesh is still perfectly
    valid — it is just inside out in one bay.
    """
    if len(STATIONS) < 8:
        raise GeometryError(f"only {len(STATIONS)} stations")

    xs = [s.x for s in STATIONS]
    if xs != sorted(xs):
        bad = next(i for i in range(1, len(xs)) if xs[i] <= xs[i - 1])
        raise GeometryError(
            f"stations are not ordered in X: station {bad} at x={xs[bad]:.4f} "
            f"follows x={xs[bad - 1]:.4f}. The loft will fold back on itself.")
    if len(set(xs)) != len(xs):
        raise GeometryError("two stations share an X; the loft has a zero-length bay")

    span = xs[-1] - xs[0]
    if abs(span - cfg.LENGTH) > 0.05:
        raise GeometryError(
            f"the station table spans {span:.4f} m, but the published length "
            f"is {cfg.LENGTH:.4f} m")

    half = cfg.WIDTH / 2.0
    for s in STATIONS:
        ring = s.ring()
        if len(ring) < 4:
            raise GeometryError(f"station x={s.x:.3f}: {len(ring)}-point ring")
        for p in ring:
            if abs(p[1]) > half + 0.002:
                raise GeometryError(
                    f"station x={s.x:.3f} reaches |Y|={abs(p[1]):.4f} m, past "
                    f"the published half width {half:.4f} m")
            if p[2] < -0.002 or p[2] > cfg.HEIGHT + 0.02:
                raise GeometryError(
                    f"station x={s.x:.3f} has a point at Z={p[2]:.4f} m, "
                    f"outside 0..{cfg.HEIGHT:.3f} m")


@visual_test("body_surface_queries", group=GROUP)
def test_surface_queries(ctx: TestContext) -> None:
    """station_at / skin_z_at / flank_half_width / nose_x / tail_x."""
    # station_at clamps rather than extrapolating off either end
    if station_at(-99.0).x != STATIONS[0].x:
        raise GeometryError("station_at does not clamp at the nose")
    if station_at(99.0).x != STATIONS[-1].x:
        raise GeometryError("station_at does not clamp at the tail")
    if not isinstance(station_at(0.0), Station):
        raise GeometryError("station_at returned something other than a Station")

    # the roof is a roof: highest over the cabin, falling toward both ends
    cabin = skin_z_at(0.0, 0.0)
    if not (skin_z_at(-1.6, 0.0) < cabin and skin_z_at(1.9, 0.0) < cabin):
        raise GeometryError(
            f"the centreline does not peak over the cabin: nose "
            f"{skin_z_at(-1.6, 0.0):.4f}, cabin {cabin:.4f}, tail "
            f"{skin_z_at(1.9, 0.0):.4f}")
    if not (0.90 <= cabin <= cfg.HEIGHT + 0.01):
        raise GeometryError(f"cabin roof at Z={cabin:.4f} m is not plausible")

    # tumblehome: the flank leans in as it rises
    low = flank_half_width(0.0, 0.60)
    high = flank_half_width(0.0, 0.95)
    if high >= low:
        raise GeometryError(
            f"no tumblehome at mid-car: half width {low:.4f} m at Z=0.60 "
            f"but {high:.4f} m at Z=0.95; the flank leans outward")
    if low > cfg.WIDTH / 2.0 + 0.002:
        raise GeometryError(
            f"flank_half_width returns {low:.4f} m, wider than the car")

    # the ends are where the ends are
    if nose_x(0.0, 0.5) > tail_x(0.0, 0.5):
        raise GeometryError("nose_x and tail_x are the wrong way round")
    if abs(nose_x(0.0, 0.5) - STATIONS[0].x) > 0.02:
        raise GeometryError(
            f"nose_x gives {nose_x(0.0, 0.5):.4f}, first station is at "
            f"{STATIONS[0].x:.4f}")

    # polygon_span reports the vertical extent of an outline at an X
    span = polygon_span([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)], 0.5)
    if span is None or abs(span[0]) > 1e-6 or abs(span[1] - 1.0) > 1e-6:
        raise GeometryError(f"polygon_span on a unit square gave {span}")
    if polygon_span([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], 5.0) is not None:
        raise GeometryError("polygon_span should return None outside the outline")

    # skin_point walks the ring without leaving the car
    for u in (0.0, 0.25, 0.5, 0.75, 1.0):
        p = skin_point(0.0, u)
        if abs(p[1]) > cfg.WIDTH / 2.0 + 0.002 or not (-0.01 <= p[2] <= cfg.HEIGHT + 0.02):
            raise GeometryError(f"skin_point(0.0, {u}) = {p} is off the car")


@visual_test("body_skin_patch", group=GROUP)
def test_skin_patch(ctx: TestContext) -> None:
    """A quad grid laid on the skin, which is how the louvres find the fastback.

    The offset is what trim rides on. If a patch does not actually follow the
    surface, everything mounted on it floats or sinks, and both look like a
    modelling mistake rather than a sampling one.
    """
    nx, nu = 6, 4
    patch = skin_patch("Patch", 0.5, 1.3, 0.30, 0.70, nx, nu)
    mu.sync()

    if len(patch.data.vertices) != (nx + 1) * (nu + 1):
        raise GeometryError(
            f"{len(patch.data.vertices)} vertices, expected "
            f"{(nx + 1) * (nu + 1)} for a {nx}x{nu} grid")
    if len(patch.data.polygons) != nx * nu:
        raise GeometryError(
            f"{len(patch.data.polygons)} faces, expected {nx * nu}")

    for v in patch.data.vertices:
        p = v.co
        if abs(p.z - skin_z_at(p.x, p.y)) > 1e-6:
            raise GeometryError(
                f"a patch vertex at ({p.x:.4f}, {p.y:.4f}, {p.z:.4f}) is "
                f"{abs(p.z - skin_z_at(p.x, p.y)) * 1000:.2f} mm off the skin")

    raised = skin_patch("PatchUp", 0.5, 1.3, 0.30, 0.70, nx, nu,
                        offset=(0.0, 0.0, 0.05))
    mu.sync()
    lift = [b.co.z - a.co.z
            for a, b in zip(patch.data.vertices, raised.data.vertices)]
    if max(abs(d - 0.05) for d in lift) > 1e-6:
        raise GeometryError(
            f"the offset did not lift the patch by 50 mm: "
            f"{min(lift) * 1000:.2f}..{max(lift) * 1000:.2f} mm")

    mu.set_material(patch, ctx.materials["steel"])
    ctx.render([patch], "body_skin_patch", view="part_quarter", margin=1.2,
               resolution=(700, 700))


@visual_test("body_material_zoning", group=GROUP)
def test_material_zoning(ctx: TestContext) -> None:
    """Bare steel over a black urethane band, rising into the bumpers."""
    # the rocker line, mid-car
    if not is_black_trim(0.0, 0.9, 0.20):
        raise GeometryError("the rocker at Z=0.20 m should be black")
    if is_black_trim(0.0, 0.9, 0.50):
        raise GeometryError("the flank at Z=0.50 m should be bare steel")

    # the band climbs at each end, so a height that is steel mid-car is black
    # over the bumpers
    if not is_black_trim(-2.10, 0.3, 0.45):
        raise GeometryError("the front bumper at Z=0.45 m should be black")
    if not is_black_trim(2.10, 0.3, 0.52):
        raise GeometryError("the rear bumper at Z=0.52 m should be black")
    if is_black_trim(0.0, 0.9, 0.45):
        raise GeometryError(
            "the band has not dropped back to the rocker line mid-car")

    shell = BodyBuilder(ctx.materials).build()
    zone_body_materials(shell, ctx.materials)
    mu.sync()

    slots = [m.name for m in shell.data.materials]
    if len(slots) < 2:
        raise GeometryError(f"shell has slots {slots}, expected steel and black")
    used = {p.material_index for p in shell.data.polygons}
    if used != {0, 1}:
        raise GeometryError(
            f"only slot(s) {sorted(used)} are used; both steel and black must "
            f"appear on the shell")

    steel = sum(1 for p in shell.data.polygons if p.material_index == 0)
    share = steel / len(shell.data.polygons)
    if not (0.45 <= share <= 0.90):
        raise GeometryError(
            f"{100 * share:.0f}% of the shell is steel, which is not a "
            f"plausible split for a car with a black band along the sill")

    ctx.render([shell], "body_material_zoning", view="hero_front_left",
               margin=1.1, resolution=(960, 640))


# ----------------------------------------------------------------- the shell
@visual_test("body_shell", reference="body/swage-line-flank.png", group=GROUP)
def test_shell(ctx: TestContext) -> None:
    """The lofted shell, against the published dimensions."""
    shell = BodyBuilder(ctx.materials).build()
    zone_body_materials(shell, ctx.materials)
    mu.sync()

    standard_checks([shell], min_polys=200)

    ok, detail = mu.is_solid(shell)
    if not ok:
        raise GeometryError(f"the shell is not a closed solid: {detail}")

    assert_dimensions(shell, (cfg.LENGTH, cfg.WIDTH, None), tol=0.02,
                      label="body shell")

    verts = _world_verts(shell)
    top = max(p.z for p in verts)
    if abs(top - cfg.HEIGHT) > 0.02:
        raise GeometryError(
            f"the roof is at {top * 1000:.0f} mm, published height is "
            f"{cfg.HEIGHT * 1000:.0f} mm")

    # the underbody has to clear the ground by roughly the published figure
    floor = min(p.z for p in verts)
    if floor < cfg.GROUND_CLEARANCE_FRONT - 0.03:
        raise GeometryError(
            f"the underbody hangs to {floor * 1000:.0f} mm, below the "
            f"{cfg.GROUND_CLEARANCE_FRONT * 1000:.0f} mm published clearance")

    ctx.render([shell], "body_shell", view="hero_front_left", margin=1.1,
               resolution=(960, 640))
    ctx.render([shell], "body_shell_side", view="side", margin=1.05,
               resolution=(1000, 460))
    ctx.render([shell], "body_shell_top", view="top", margin=1.05,
               resolution=(1000, 560))


@visual_test("body_panel_thickness", group=GROUP)
def test_panel_thickness(ctx: TestContext) -> None:
    """Solidify gives the shell a wall, and one of the right thickness.

    `use_even_offset` is deliberately off. It scales the inset by 1/cos at each
    crease, and on a body creased this sharply the inner surface passes through
    itself. The mesh still reports as a closed manifold, but the exact boolean
    solver then reads one half of the car as inside out, and door cuts return
    nothing on that side.
    """
    shell = BodyBuilder(ctx.materials).build()
    mu.sync()

    crossings = _hits(shell, Vector((0.0, 2.0, 0.60)), Vector((0.0, -1.0, 0.0)))
    if len(crossings) < 4:
        raise GeometryError(
            f"a ray across the flank crosses the shell {len(crossings)} "
            f"time(s); a walled shell gives 4 (outer, inner, inner, outer)")

    wall = abs(crossings[0].y - crossings[1].y)
    if abs(wall - cfg.BODY_PANEL_THICKNESS) > 0.006:
        raise GeometryError(
            f"the flank is {wall * 1000:.1f} mm thick, expected "
            f"{cfg.BODY_PANEL_THICKNESS * 1000:.1f} mm")


@visual_test("body_wheel_arches", reference="body/arch-rear-wheel.png",
             group=GROUP)
def test_wheel_arches(ctx: TestContext) -> None:
    """All four arches are actually cut, and clear their tyres."""
    shell = BodyBuilder(ctx.materials).build()
    mu.sync()
    verts = _world_verts(shell)

    arches = (("front", BodyBuilder.ARCH_FRONT, cfg.WHEEL_FRONT),
              ("rear", BodyBuilder.ARCH_REAR, cfg.WHEEL_REAR))

    for label, (axle_x, cz, radius), spec in arches:
        if radius <= spec.radius:
            raise GeometryError(
                f"the {label} arch radius {radius * 1000:.0f} mm is no bigger "
                f"than the {spec.radius * 1000:.0f} mm tyre")

        for sign in (1, -1):
            inside = [p for p in verts
                      if BodyBuilder.ARCH_INBOARD + 0.02 < sign * p.y
                      < BodyBuilder.ARCH_OUTBOARD - 0.02
                      and ((p.x - axle_x) ** 2 + (p.z - cz) ** 2) ** 0.5
                      < radius - 0.02]
            if inside:
                worst = min(inside,
                            key=lambda p: (p.x - axle_x) ** 2 + (p.z - cz) ** 2)
                raise GeometryError(
                    f"{len(inside)} shell vertices sit inside the {label} "
                    f"{'left' if sign > 0 else 'right'} arch — closest at "
                    f"({worst.x:.3f}, {worst.y:.3f}, {worst.z:.3f}). The arch "
                    f"boolean did not cut.")

    ctx.render([shell], "body_wheel_arches", view="side", margin=1.05,
               resolution=(1000, 460))
