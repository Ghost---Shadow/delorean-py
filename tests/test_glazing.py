"""Visual unit tests for delorean.glazing.

References: references/parts/glazing/greenhouse-side.png,
            references/parts/glazing/quarter-window-sail.png

Glass is the part of this model most likely to be wrong in a way that renders
fine. A pane built from the surface parameter rather than from its own aperture
outline spills across the roof; a pane at the wrong inset floats above the
steel or vanishes inside it; an aperture that never got cut leaves the glass
sitting on a solid roof. None of that raises anything on its own.

So these tests check three things the eye is bad at: that each aperture is
genuinely open, that each pane stays inside the outline it belongs to, and that
it sits *below* the surrounding skin rather than through it.
"""
from __future__ import annotations

import bpy
from mathutils import Vector

from delorean import body as body_mod
from delorean import config as cfg
from delorean import doors as doors_mod
from delorean import glazing
from delorean import mesh_utils as mu
from delorean.glazing import (BACKLIGHT_PLAN, GLASS_INSET, GLASS_OVERLAP,
                              QUARTER_OUTLINE, SIDE_OUTLINE, WINDSCREEN_PLAN,
                              GlazingBuilder, build_glazing, cut_apertures)

from .harness import (GeometryError, TestContext, standard_checks, visual_test)

GROUP = "glazing"


def _world_verts(ob: bpy.types.Object) -> list[Vector]:
    return [ob.matrix_world @ Vector(v.co) for v in ob.data.vertices]


def _hits(ob: bpy.types.Object, origin: Vector, direction: Vector) -> int:
    inv = ob.matrix_world.inverted()
    o = inv @ origin
    d = (inv.to_3x3() @ direction).normalized()
    count, cursor = 0, o
    for _ in range(16):
        ok, location, _n, _i = ob.ray_cast(cursor, d, distance=12.0)
        if not ok:
            break
        count += 1
        cursor = location + d * 1e-4
    return count


def _centroid(outline) -> tuple[float, float]:
    return (sum(p[0] for p in outline) / len(outline),
            sum(p[1] for p in outline) / len(outline))


def _bounds(obs, axis: int) -> tuple[float, float]:
    pts = [p[axis] for ob in obs for p in _world_verts(ob)]
    return min(pts), max(pts)


# -------------------------------------------------------------- the apertures
@visual_test("glazing_apertures_open", group=GROUP)
def test_apertures_open(ctx: TestContext) -> None:
    """cut_apertures opens the greenhouse, and only the greenhouse.

    Counted by ray, not by eye: a closed shell returns four crossings on a
    vertical line through the cabin (roof out, roof in, floor in, floor out).
    Opening the roof takes two of them away. A boolean that silently no-ops
    leaves all four, and the glass is then laid over solid steel.
    """
    shell = body_mod.BodyBuilder(ctx.materials).build()
    mu.sync()

    down = Vector((0.0, 0.0, -1.0))
    probes = {
        "windscreen": _centroid(WINDSCREEN_PLAN),
        "backlight": _centroid(BACKLIGHT_PLAN),
    }
    before = {name: _hits(shell, Vector((x, y, 2.0)), down)
              for name, (x, y) in probes.items()}
    for name, n in before.items():
        if n < 4:
            raise GeometryError(
                f"the shell is already open over the {name} before cutting "
                f"({n} crossings, expected 4)")

    cut_apertures(shell)
    mu.sync()

    after = {name: _hits(shell, Vector((x, y, 2.0)), down)
             for name, (x, y) in probes.items()}
    for name, n in after.items():
        if n != before[name] - 2:
            raise GeometryError(
                f"the {name} aperture did not open: {before[name]} crossings "
                f"before the cut, {n} after — expected {before[name] - 2}")

    # the quarter windows are cut across the car, not down through it
    qx, qz = _centroid(QUARTER_OUTLINE)
    across = _hits(shell, Vector((qx, 2.0, qz)), Vector((0.0, -1.0, 0.0)))
    if across >= 4:
        raise GeometryError(
            f"the quarter windows are still closed: {across} crossings "
            f"through the sail panels at (x={qx:.3f}, z={qz:.3f})")

    ctx.render([shell], "glazing_apertures_open", view="hero_front_left",
               margin=1.1, resolution=(960, 640))
    ctx.render([shell], "glazing_apertures_top", view="top", margin=1.05,
               resolution=(1000, 560))


# ------------------------------------------------------------------ the panes
@visual_test("glazing_windscreen", group=GROUP)
def test_windscreen(ctx: TestContext) -> None:
    """The screen stays inside its aperture instead of spilling over the roof."""
    pane = GlazingBuilder(ctx.materials).windscreen()
    mu.sync()

    standard_checks([pane])

    xs = [p[0] for p in WINDSCREEN_PLAN]
    lo, hi = _bounds([pane], 0)
    slack = GLASS_OVERLAP + 0.002
    if lo < min(xs) - slack or hi > max(xs) + slack:
        raise GeometryError(
            f"the windscreen spans X {lo:.4f}..{hi:.4f}, outside its aperture "
            f"{min(xs):.4f}..{max(xs):.4f} (+{GLASS_OVERLAP * 1000:.0f} mm "
            f"overlap). It is being built from the surface, not the outline.")

    _check_inset(pane, "windscreen")

    ctx.render([pane], "glazing_windscreen", view="part_quarter", margin=1.2)


@visual_test("glazing_backlight", group=GROUP)
def test_backlight(ctx: TestContext) -> None:
    """The rear screen, which the louvres sit over."""
    pane = GlazingBuilder(ctx.materials).backlight()
    mu.sync()

    standard_checks([pane])

    xs = [p[0] for p in BACKLIGHT_PLAN]
    lo, hi = _bounds([pane], 0)
    slack = GLASS_OVERLAP + 0.002
    if lo < min(xs) - slack or hi > max(xs) + slack:
        raise GeometryError(
            f"the backlight spans X {lo:.4f}..{hi:.4f}, outside its aperture "
            f"{min(xs):.4f}..{max(xs):.4f}")

    # it is tinted, not clear: under the louvres it should read near-black
    if pane.data.materials[0].name == ctx.materials["glass"].name:
        raise GeometryError(
            "the backlight is using clear glass; it sits under the louvres "
            "and should be the dark glass")

    _check_inset(pane, "backlight")

    ctx.render([pane], "glazing_backlight", view="part_quarter", margin=1.2)


@visual_test("glazing_side", reference="glazing/greenhouse-side.png", group=GROUP)
def test_side(ctx: TestContext) -> None:
    """Door glass fills the daylight opening it shares with doors.py."""
    builder = GlazingBuilder(ctx.materials)
    panes = [builder.side("L", 1), builder.side("R", -1)]
    mu.sync()

    standard_checks(panes)

    xs = [p[0] for p in SIDE_OUTLINE]
    lo, hi = _bounds(panes, 0)
    if lo < min(xs) - 0.002 or hi > max(xs) + 0.002:
        raise GeometryError(
            f"the side glass spans X {lo:.4f}..{hi:.4f}, outside the door's "
            f"window outline {min(xs):.4f}..{max(xs):.4f}")

    # it must sit inside the flank, not proud of it
    for pane in panes:
        for p in _world_verts(pane):
            skin = body_mod.flank_half_width(p.x, p.z)
            if abs(p.y) > skin - GLASS_INSET + 0.004:
                raise GeometryError(
                    f"{pane.name}: glass at |Y|={abs(p.y):.4f} m stands proud "
                    f"of the {skin:.4f} m flank")

    ctx.render(panes, "glazing_side", view="part_quarter", margin=1.25)


@visual_test("glazing_quarter", reference="glazing/quarter-window-sail.png",
             group=GROUP)
def test_quarter(ctx: TestContext) -> None:
    """The small sail-panel windows behind the doors."""
    builder = GlazingBuilder(ctx.materials)
    panes = [builder.quarter("L", 1), builder.quarter("R", -1)]
    mu.sync()

    standard_checks(panes)

    left, right = panes
    ly = [p.y for p in _world_verts(left)]
    ry = [p.y for p in _world_verts(right)]
    if min(ly) <= 0.0 or max(ry) >= 0.0:
        raise GeometryError(
            "the quarter windows are not on opposite sides of the car")
    if abs(min(ly) + max(ry)) > 0.002:
        raise GeometryError(
            f"the quarter windows are not symmetric: left starts at "
            f"Y={min(ly):.4f}, right at Y={max(ry):.4f}")

    ctx.render(panes, "glazing_quarter", view="part_quarter", margin=1.3)


@visual_test("glazing_set", reference="glazing/greenhouse-side.png", group=GROUP)
def test_glazing_set(ctx: TestContext) -> None:
    """Six panes, and the door glass swings with the door it belongs to."""
    shell = body_mod.BodyBuilder(ctx.materials).build()
    doors = doors_mod.build_doors(shell, ctx.materials, cfg.RigConfig())
    glazing.cut_apertures(shell)
    panes = build_glazing(ctx.materials, doors)
    mu.sync()

    standard_checks(panes)
    if len(panes) != 6:
        raise GeometryError(
            f"expected 6 panes (screen, backlight, 2 side, 2 quarter), got "
            f"{len(panes)}: {[p.name for p in panes]}")

    parented = {p.name: (p.parent.name if p.parent else None) for p in panes}
    for side in ("L", "R"):
        want = f"Door_{side}"
        got = parented.get(f"Glass_Side_{side}")
        if got != want:
            raise GeometryError(
                f"Glass_Side_{side} is parented to {got!r}, expected {want!r} "
                f"— it will stay behind when the door opens")
    for side in ("L", "R"):
        if parented.get(f"Glass_Quarter_{side}") is not None:
            raise GeometryError(
                f"Glass_Quarter_{side} is parented to a door; the sail panel "
                f"does not move")

    # and it really does travel: open the doors and watch the glass follow
    before = {p.name: max(v.z for v in _world_verts(p)) for p in panes}
    doors_mod.pose_doors(doors, cfg.RigConfig.doors_open(52.0))
    mu.sync()
    after = {p.name: max(v.z for v in _world_verts(p)) for p in panes}

    for side in ("L", "R"):
        name = f"Glass_Side_{side}"
        if after[name] - before[name] < 0.10:
            raise GeometryError(
                f"{name} rose {(after[name] - before[name]) * 1000:.0f} mm "
                f"when the door opened; it is not following the panel")
    if abs(after["Glass_Windscreen"] - before["Glass_Windscreen"]) > 1e-6:
        raise GeometryError("the windscreen moved when the doors opened")

    ctx.render([shell] + doors + panes, "glazing_set",
               view="hero_front_left", margin=1.15, resolution=(960, 660))


# ----------------------------------------------------------------- shared
def _check_inset(pane: bpy.types.Object, label: str) -> None:
    """Every vertex sits GLASS_INSET below the skin it is set into."""
    worst = 0.0
    for p in _world_verts(pane):
        skin = body_mod.skin_z_at(p.x, p.y)
        worst = max(worst, abs((skin - p.z) - GLASS_INSET))
    if worst > 0.006:
        raise GeometryError(
            f"the {label} is up to {worst * 1000:.1f} mm off its "
            f"{GLASS_INSET * 1000:.0f} mm inset; it is not following the "
            f"surface it is set into")
